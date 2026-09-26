// SPDX-License-Identifier: GPL-2.0
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/videodev2.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <dirent.h>
#include <limits.h>

#define VIDEO_DEV "/dev/video0"
#define OTP_CACHE "/run/mipad2-camera/otp.bin"
#define OTP_SYSFS "/sys/bus/nvmem/devices/mipad2-t4ka3-otp/nvmem"
#define OTP_SIZE 578
#define FALLBACK_INF 237
#define FALLBACK_MACRO 366
#define REAR_INPUT 1
#define NBUFS 4

struct mm_buf {
    void *ptr;
    size_t len;
};

static int xioctl(int fd, unsigned long req, void *arg)
{
    int r;
    do {
        r = ioctl(fd, req, arg);
    } while (r < 0 && errno == EINTR);
    return r;
}

static int read_exact(const char *path, uint8_t *buf, size_t n)
{
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0)
        return -1;

    size_t off = 0;
    while (off < n) {
        ssize_t r = read(fd, buf + off, n - off);
        if (r <= 0) {
            close(fd);
            return -1;
        }
        off += (size_t)r;
    }

    uint8_t extra;
    ssize_t r = read(fd, &extra, 1);
    close(fd);
    return r == 0 ? 0 : -1;
}

static int group_ok(const uint8_t *d, size_t start, size_t size)
{
    unsigned sum = 0;

    if (start + size > OTP_SIZE || size < 3 || d[start] != 1)
        return 0;

    for (size_t i = start + 1; i < start + size - 1; i++)
        sum += d[i];

    return (sum % 255) == d[start + size - 1];
}

static int otp_focus_range(int *inf, int *macro, const char **source)
{
    uint8_t d[OTP_SIZE];
    const char *env = getenv("MIPAD2_OTP_PATH");
    const char *paths[] = { env, OTP_CACHE, OTP_SYSFS, NULL };

    for (int p = 0; paths[p] || p < 3; p++) {
        const char *path = paths[p];
        if (!path || !*path)
            continue;
        if (read_exact(path, d, sizeof(d)) < 0)
            continue;

        if (!group_ok(d, 0x00, 0x10) ||
            !group_ok(d, 0x10, 0x10) ||
            !group_ok(d, 0x20, 0x110) ||
            !group_ok(d, 0x130, 0x112))
            continue;

        int i = ((int)d[0x13] << 8) | d[0x14];
        int m = ((int)d[0x15] << 8) | d[0x16];
        if (i < 0 || i >= m || m > 1023)
            continue;

        *inf = i;
        *macro = m;
        *source = path;
        return 0;
    }

    *inf = FALLBACK_INF;
    *macro = FALLBACK_MACRO;
    *source = "fallback";
    return -1;
}

static int read_name(const char *path, char *buf, size_t n)
{
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0)
        return -1;
    ssize_t r = read(fd, buf, n - 1);
    close(fd);
    if (r <= 0)
        return -1;
    buf[r] = 0;
    char *nl = strchr(buf, '\n');
    if (nl)
        *nl = 0;
    return 0;
}

static int find_focus_dev(char *out, size_t n)
{
    DIR *d = opendir("/sys/class/video4linux");
    if (!d)
        return -1;

    struct dirent *de;
    int found = -1;

    while ((de = readdir(d))) {
        if (strncmp(de->d_name, "v4l-subdev", 11))
            continue;

        char p[PATH_MAX], name[256];
        snprintf(p, sizeof(p), "/sys/class/video4linux/%s/name", de->d_name);
        if (read_name(p, name, sizeof(name)) < 0)
            continue;

        if (strstr(name, "dw9719") || strstr(name, "dw9761")) {
            snprintf(out, n, "/dev/%s", de->d_name);
            found = 0;
            break;
        }
    }

    closedir(d);
    return found;
}

static int focus_get(int fd, int *v)
{
    struct v4l2_control c = { .id = V4L2_CID_FOCUS_ABSOLUTE };
    if (xioctl(fd, VIDIOC_G_CTRL, &c) < 0)
        return -1;
    *v = c.value;
    return 0;
}

static int focus_set(int fd, int v)
{
    struct v4l2_control c = {
        .id = V4L2_CID_FOCUS_ABSOLUTE,
        .value = v,
    };
    return xioctl(fd, VIDIOC_S_CTRL, &c);
}

static int luma_layout(uint32_t fmt, unsigned width, unsigned bpl,
                       unsigned *stride, unsigned *pixel_step, unsigned *pixel_off)
{
    switch (fmt) {
    case V4L2_PIX_FMT_YUV420:
    case V4L2_PIX_FMT_YVU420:
    case V4L2_PIX_FMT_NV12:
    case V4L2_PIX_FMT_NV21:
    case V4L2_PIX_FMT_NV16:
    case V4L2_PIX_FMT_YUV422P:
        *stride = bpl ? bpl : width;
        *pixel_step = 1;
        *pixel_off = 0;
        return 0;
    case V4L2_PIX_FMT_YUYV:
        *stride = bpl ? bpl : width * 2;
        *pixel_step = 2;
        *pixel_off = 0;
        return 0;
    case V4L2_PIX_FMT_UYVY:
        *stride = bpl ? bpl : width * 2;
        *pixel_step = 2;
        *pixel_off = 1;
        return 0;
    default:
        return -1;
    }
}

static inline int y_at(const uint8_t *p, unsigned stride, unsigned step,
                       unsigned off, unsigned x, unsigned y)
{
    return p[(size_t)y * stride + (size_t)x * step + off];
}

static double sharpness(const uint8_t *p, size_t bytes,
                        unsigned w, unsigned h, unsigned stride,
                        unsigned step, unsigned off)
{
    if (w < 32 || h < 32)
        return 0.0;

    size_t min_bytes = (size_t)stride * h;
    if (bytes < min_bytes)
        return 0.0;

    unsigned x0 = w / 8, x1 = w * 7 / 8;
    unsigned y0 = h / 8, y1 = h * 7 / 8;
    uint64_t total = 0, count = 0;

    for (unsigned y = y0 + 2; y + 2 < y1; y += 4) {
        for (unsigned x = x0 + 2; x + 2 < x1; x += 4) {
            int gx = y_at(p, stride, step, off, x + 1, y) -
                     y_at(p, stride, step, off, x - 1, y);
            int gy = y_at(p, stride, step, off, x, y + 1) -
                     y_at(p, stride, step, off, x, y - 1);
            total += (uint64_t)(gx * gx + gy * gy);
            count++;
        }
    }

    return count ? (double)total / (double)count : 0.0;
}

static int dequeue_frame(int fd, struct mm_buf *bufs, unsigned count,
                         struct v4l2_buffer *b)
{
    struct pollfd pfd = { .fd = fd, .events = POLLIN };
    int pr;
    do {
        pr = poll(&pfd, 1, 2500);
    } while (pr < 0 && errno == EINTR);
    if (pr <= 0)
        return -1;

    memset(b, 0, sizeof(*b));
    b->type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    b->memory = V4L2_MEMORY_MMAP;
    if (xioctl(fd, VIDIOC_DQBUF, b) < 0)
        return -1;
    if (b->index >= count)
        return -1;
    if (b->bytesused > bufs[b->index].len)
        b->bytesused = bufs[b->index].len;
    return 0;
}

static int requeue_frame(int fd, struct v4l2_buffer *b)
{
    return xioctl(fd, VIDIOC_QBUF, b);
}

static double measure_focus(int vfd, int ffd, struct mm_buf *bufs, unsigned nbufs,
                            int pos, unsigned w, unsigned h, unsigned stride,
                            unsigned step, unsigned off)
{
    if (focus_set(ffd, pos) < 0)
        return -1.0;

    usleep(80000);

    double total = 0.0;
    int scored = 0;

    for (int i = 0; i < 4; i++) {
        struct v4l2_buffer b;
        if (dequeue_frame(vfd, bufs, nbufs, &b) < 0)
            return -1.0;

        if (i >= 2) {
            total += sharpness(bufs[b.index].ptr, b.bytesused,
                               w, h, stride, step, off);
            scored++;
        }

        if (requeue_frame(vfd, &b) < 0)
            return -1.0;
    }

    return scored ? total / scored : -1.0;
}

static int simple_action(const char *action, int ffd, int inf, int macro)
{
    int pos;
    if (!strcmp(action, "far"))
        pos = inf;
    else if (!strcmp(action, "near"))
        pos = macro;
    else if (!strcmp(action, "mid"))
        pos = inf + (macro - inf) / 2;
    else
        return -1;

    if (focus_set(ffd, pos) < 0) {
        perror("VIDIOC_S_CTRL focus");
        return 1;
    }

    printf("focus=%d\n", pos);
    return 0;
}

int main(int argc, char **argv)
{
    const char *action = argc > 1 ? argv[1] : "auto";
    int inf, macro;
    const char *otp_source;
    int otp_ok = otp_focus_range(&inf, &macro, &otp_source) == 0;

    printf("AF range=%d..%d source=%s%s\n",
           inf, macro, otp_source, otp_ok ? "" : " (fallback)");

    if (!strcmp(action, "range"))
        return 0;

    char focus_dev[PATH_MAX];
    if (find_focus_dev(focus_dev, sizeof(focus_dev)) < 0) {
        fprintf(stderr, "DW9719/DW9761 focus subdevice not found\n");
        return 2;
    }

    int ffd = open(focus_dev, O_RDWR | O_CLOEXEC);
    if (ffd < 0) {
        perror(focus_dev);
        return 2;
    }

    if (strcmp(action, "auto")) {
        int r = simple_action(action, ffd, inf, macro);
        close(ffd);
        if (r < 0) {
            fprintf(stderr, "usage: %s [auto|far|near|mid|range]\n", argv[0]);
            return 2;
        }
        return r;
    }

    int old_focus = -1;
    focus_get(ffd, &old_focus);

    int vfd = open(VIDEO_DEV, O_RDWR | O_NONBLOCK | O_CLOEXEC);
    if (vfd < 0) {
        perror(VIDEO_DEV);
        close(ffd);
        return 2;
    }

    int old_input = 0;
    if (xioctl(vfd, VIDIOC_G_INPUT, &old_input) < 0)
        old_input = 0;

    int input = REAR_INPUT;
    if (xioctl(vfd, VIDIOC_S_INPUT, &input) < 0) {
        perror("VIDIOC_S_INPUT rear");
        close(vfd);
        close(ffd);
        return 3;
    }

    struct v4l2_format fmt = { .type = V4L2_BUF_TYPE_VIDEO_CAPTURE };
    if (xioctl(vfd, VIDIOC_G_FMT, &fmt) < 0) {
        perror("VIDIOC_G_FMT");
        goto fail_restore;
    }

    unsigned stride, pixel_step, pixel_off;
    if (luma_layout(fmt.fmt.pix.pixelformat, fmt.fmt.pix.width,
                    fmt.fmt.pix.bytesperline,
                    &stride, &pixel_step, &pixel_off) < 0) {
        fprintf(stderr, "unsupported pixel format %.4s\n",
                (char *)&fmt.fmt.pix.pixelformat);
        goto fail_restore;
    }

    struct v4l2_requestbuffers req = {
        .count = NBUFS,
        .type = V4L2_BUF_TYPE_VIDEO_CAPTURE,
        .memory = V4L2_MEMORY_MMAP,
    };
    if (xioctl(vfd, VIDIOC_REQBUFS, &req) < 0 || req.count < 2) {
        perror("VIDIOC_REQBUFS");
        goto fail_restore;
    }

    struct mm_buf bufs[NBUFS] = {0};
    unsigned nbufs = req.count > NBUFS ? NBUFS : req.count;

    for (unsigned i = 0; i < nbufs; i++) {
        struct v4l2_buffer b = {
            .type = V4L2_BUF_TYPE_VIDEO_CAPTURE,
            .memory = V4L2_MEMORY_MMAP,
            .index = i,
        };
        if (xioctl(vfd, VIDIOC_QUERYBUF, &b) < 0) {
            perror("VIDIOC_QUERYBUF");
            goto fail_unmap;
        }

        bufs[i].len = b.length;
        bufs[i].ptr = mmap(NULL, b.length, PROT_READ | PROT_WRITE,
                           MAP_SHARED, vfd, b.m.offset);
        if (bufs[i].ptr == MAP_FAILED) {
            bufs[i].ptr = NULL;
            perror("mmap");
            goto fail_unmap;
        }

        if (xioctl(vfd, VIDIOC_QBUF, &b) < 0) {
            perror("VIDIOC_QBUF");
            goto fail_unmap;
        }
    }

    enum v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    if (xioctl(vfd, VIDIOC_STREAMON, &type) < 0) {
        perror("VIDIOC_STREAMON");
        goto fail_unmap;
    }

    int span = macro - inf;
    int coarse_step = span / 12;
    if (coarse_step < 6)
        coarse_step = 6;

    double best_score = -1.0;
    int best = inf;

    printf("video=%ux%u %.4s stride=%u focusdev=%s oldfocus=%d\n",
           fmt.fmt.pix.width, fmt.fmt.pix.height,
           (char *)&fmt.fmt.pix.pixelformat, stride, focus_dev, old_focus);

    for (int p = inf; p <= macro; p += coarse_step) {
        double s = measure_focus(vfd, ffd, bufs, nbufs, p,
                                 fmt.fmt.pix.width, fmt.fmt.pix.height,
                                 stride, pixel_step, pixel_off);
        if (s < 0)
            goto fail_stream;
        printf("coarse %d %.2f\n", p, s);
        if (s > best_score) {
            best_score = s;
            best = p;
        }
    }
    if ((macro - inf) % coarse_step) {
        double s = measure_focus(vfd, ffd, bufs, nbufs, macro,
                                 fmt.fmt.pix.width, fmt.fmt.pix.height,
                                 stride, pixel_step, pixel_off);
        if (s < 0)
            goto fail_stream;
        printf("coarse %d %.2f\n", macro, s);
        if (s > best_score) {
            best_score = s;
            best = macro;
        }
    }

    int fine_lo = best - coarse_step;
    int fine_hi = best + coarse_step;
    if (fine_lo < inf) fine_lo = inf;
    if (fine_hi > macro) fine_hi = macro;

    for (int p = fine_lo; p <= fine_hi; p += 2) {
        double s = measure_focus(vfd, ffd, bufs, nbufs, p,
                                 fmt.fmt.pix.width, fmt.fmt.pix.height,
                                 stride, pixel_step, pixel_off);
        if (s < 0)
            goto fail_stream;
        printf("fine %d %.2f\n", p, s);
        if (s > best_score) {
            best_score = s;
            best = p;
        }
    }

    if (focus_set(ffd, best) < 0)
        perror("final focus");

    xioctl(vfd, VIDIOC_STREAMOFF, &type);
    for (unsigned i = 0; i < nbufs; i++)
        if (bufs[i].ptr)
            munmap(bufs[i].ptr, bufs[i].len);

    xioctl(vfd, VIDIOC_S_INPUT, &old_input);
    close(vfd);
    close(ffd);

    printf("BEST focus=%d score=%.2f\n", best, best_score);
    return 0;

fail_stream:
    xioctl(vfd, VIDIOC_STREAMOFF, &type);
fail_unmap:
    for (unsigned i = 0; i < nbufs; i++)
        if (bufs[i].ptr)
            munmap(bufs[i].ptr, bufs[i].len);
fail_restore:
    xioctl(vfd, VIDIOC_S_INPUT, &old_input);
    if (old_focus >= 0)
        focus_set(ffd, old_focus);
    close(vfd);
    close(ffd);
    return 4;
}
