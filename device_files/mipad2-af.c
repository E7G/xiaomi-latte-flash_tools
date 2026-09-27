#include <errno.h>
#include <fcntl.h>
#include <linux/videodev2.h>
#include <linux/v4l2-controls.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#define NBUF 4
#define LOW_DETAIL_THRESHOLD 0.02

struct mapbuf { void *ptr; size_t len; };

static int xioctl(int fd, unsigned long req, void *arg)
{
    int r;
    do r = ioctl(fd, req, arg); while (r < 0 && errno == EINTR);
    return r;
}

static void msleep(unsigned ms)
{
    struct timespec ts = { .tv_sec = ms / 1000, .tv_nsec = (long)(ms % 1000) * 1000000L };
    nanosleep(&ts, NULL);
}

static double edge_score(const uint8_t *y, int width, int height, int stride)
{
    int x0 = width / 4, x1 = width * 3 / 4;
    int y0 = height / 4, y1 = height * 3 / 4;
    uint64_t sum = 0, cnt = 0;
    for (int yy = y0 + 1; yy < y1 - 1; yy += 2) {
        const uint8_t *row = y + (size_t)yy * stride;
        const uint8_t *prev = y + (size_t)(yy - 1) * stride;
        const uint8_t *next = y + (size_t)(yy + 1) * stride;
        for (int x = x0 + 1; x < x1 - 1; x += 2) {
            int gx = abs((int)row[x + 1] - (int)row[x - 1]);
            int gy = abs((int)next[x] - (int)prev[x]);
            sum += (uint64_t)gx + (uint64_t)gy;
            cnt++;
        }
    }
    return cnt ? (double)sum / (double)cnt : 0.0;
}

static int get_focus(int fd, int *pos)
{
    struct v4l2_control c = { .id = V4L2_CID_FOCUS_ABSOLUTE };
    if (xioctl(fd, VIDIOC_G_CTRL, &c) < 0)
        return -1;
    *pos = c.value;
    return 0;
}

static int set_focus(int fd, int pos)
{
    struct v4l2_control c = { .id = V4L2_CID_FOCUS_ABSOLUTE, .value = pos };
    return xioctl(fd, VIDIOC_S_CTRL, &c);
}

static double capture_metric(int vfd, struct mapbuf *bufs, int width, int height, int stride)
{
    double s[3] = {0};
    int kept = 0;
    for (int i = 0; i < 5; i++) {
        struct v4l2_buffer b = {0};
        b.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        b.memory = V4L2_MEMORY_MMAP;
        if (xioctl(vfd, VIDIOC_DQBUF, &b) < 0) {
            perror("VIDIOC_DQBUF");
            return -1.0;
        }
        if (i >= 2 && kept < 3)
            s[kept++] = edge_score((const uint8_t *)bufs[b.index].ptr, width, height, stride);
        if (xioctl(vfd, VIDIOC_QBUF, &b) < 0) {
            perror("VIDIOC_QBUF");
            return -1.0;
        }
    }
    if (kept != 3) return -1.0;
    if (s[0] > s[1]) { double t=s[0]; s[0]=s[1]; s[1]=t; }
    if (s[1] > s[2]) { double t=s[1]; s[1]=s[2]; s[2]=t; }
    if (s[0] > s[1]) { double t=s[0]; s[0]=s[1]; s[1]=t; }
    return s[1];
}

static int load_otp_bounds(int *fmin, int *fmax)
{
    static const char path[] = "/sys/bus/nvmem/devices/mipad2-t4ka3-otp/nvmem";
    uint8_t af[16];
    unsigned sum = 0;
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0)
        return -1;
    ssize_t n = pread(fd, af, sizeof(af), 16);
    close(fd);
    if (n != (ssize_t)sizeof(af) || af[0] != 0x01)
        return -1;
    for (int i = 1; i <= 14; i++) sum += af[i];
    if ((sum % 255) != af[15])
        return -1;
    int inf = ((int)af[3] << 8) | af[4];
    int macro = ((int)af[5] << 8) | af[6];
    if (inf < 0 || macro > 1023 || inf >= macro)
        return -1;
    *fmin = inf;
    *fmax = macro;
    return 0;
}

static double score_pos(int vfd, int lfd, struct mapbuf *bufs, int w, int h, int stride, int pos)
{
    if (set_focus(lfd, pos) < 0) {
        perror("set focus");
        return -1.0;
    }
    msleep(140);
    double sc = capture_metric(vfd, bufs, w, h, stride);
    printf("focus=%d score=%.6f\n", pos, sc);
    fflush(stdout);
    return sc;
}

int main(int argc, char **argv)
{
    int fmin = 237, fmax = 366;
    int otp_bounds = (load_otp_bounds(&fmin, &fmax) == 0);
    if (argc >= 3) {
        fmin = atoi(argv[1]);
        fmax = atoi(argv[2]);
        otp_bounds = 0;
    }
    if (fmin < 0 || fmax > 1023 || fmin >= fmax) {
        fprintf(stderr, "invalid focus range\n");
        return 2;
    }

    int vfd = open("/dev/video0", O_RDWR | O_CLOEXEC);
    int lfd = open("/dev/v4l-subdev6", O_RDWR | O_CLOEXEC);
    if (vfd < 0 || lfd < 0) { perror("open"); return 1; }

    int original_focus = fmin;
    if (get_focus(lfd, &original_focus) < 0)
        original_focus = fmin;

    int input = 1;
    if (xioctl(vfd, VIDIOC_S_INPUT, &input) < 0) { perror("VIDIOC_S_INPUT"); return 1; }

    struct v4l2_format fmt = {0};
    fmt.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    if (xioctl(vfd, VIDIOC_G_FMT, &fmt) < 0) { perror("VIDIOC_G_FMT"); return 1; }
    if (fmt.fmt.pix.pixelformat != V4L2_PIX_FMT_YUV420) {
        fprintf(stderr, "unsupported pixel format 0x%08x\n", fmt.fmt.pix.pixelformat);
        return 3;
    }
    int w = fmt.fmt.pix.width, h = fmt.fmt.pix.height;
    int stride = fmt.fmt.pix.bytesperline ? (int)fmt.fmt.pix.bytesperline : w;
    fprintf(stderr, "format=%dx%d stride=%d range=%d..%d source=%s\n", w, h, stride, fmin, fmax, otp_bounds ? "otp" : "fallback/cli");

    struct v4l2_requestbuffers req = {0};
    req.count = NBUF;
    req.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    req.memory = V4L2_MEMORY_MMAP;
    if (xioctl(vfd, VIDIOC_REQBUFS, &req) < 0) { perror("VIDIOC_REQBUFS"); return 1; }
    if (req.count < 2) { fprintf(stderr, "not enough buffers\n"); return 1; }

    struct mapbuf bufs[NBUF] = {0};
    for (unsigned i = 0; i < req.count && i < NBUF; i++) {
        struct v4l2_buffer b = {0};
        b.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        b.memory = V4L2_MEMORY_MMAP;
        b.index = i;
        if (xioctl(vfd, VIDIOC_QUERYBUF, &b) < 0) { perror("VIDIOC_QUERYBUF"); return 1; }
        bufs[i].len = b.length;
        bufs[i].ptr = mmap(NULL, b.length, PROT_READ | PROT_WRITE, MAP_SHARED, vfd, b.m.offset);
        if (bufs[i].ptr == MAP_FAILED) { perror("mmap"); return 1; }
        if (xioctl(vfd, VIDIOC_QBUF, &b) < 0) { perror("VIDIOC_QBUF initial"); return 1; }
    }

    enum v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    if (xioctl(vfd, VIDIOC_STREAMON, &type) < 0) { perror("VIDIOC_STREAMON"); return 1; }

    // Warm the AtomISP pipeline once, then never restart it during the search.
    for (int i = 0; i < 6; i++) {
        struct v4l2_buffer b = {0};
        b.type = type; b.memory = V4L2_MEMORY_MMAP;
        if (xioctl(vfd, VIDIOC_DQBUF, &b) < 0) { perror("warm DQBUF"); return 1; }
        if (xioctl(vfd, VIDIOC_QBUF, &b) < 0) { perror("warm QBUF"); return 1; }
    }

    int best = fmin;
    double bests = -1.0;
    for (int p = fmin; p <= fmax; p += 16) {
        double s = score_pos(vfd, lfd, bufs, w, h, stride, p);
        if (s > bests) { bests = s; best = p; }
    }
    if ((fmax - fmin) % 16) {
        double s = score_pos(vfd, lfd, bufs, w, h, stride, fmax);
        if (s > bests) { bests = s; best = fmax; }
    }

    int lo = best - 16; if (lo < fmin) lo = fmin;
    int hi = best + 16; if (hi > fmax) hi = fmax;
    for (int p = lo; p <= hi; p += 4) {
        double s = score_pos(vfd, lfd, bufs, w, h, stride, p);
        if (s > bests) { bests = s; best = p; }
    }

    if (bests >= 0.0 && bests < LOW_DETAIL_THRESHOLD) {
        if (set_focus(lfd, original_focus) < 0)
            perror("restore original focus");
        printf("LOW_DETAIL score=%.6f restore=%d threshold=%.6f\n",
               bests, original_focus, LOW_DETAIL_THRESHOLD);
    } else {
        if (set_focus(lfd, best) < 0)
            perror("set final focus");
        printf("BEST focus=%d score=%.6f\n", best, bests);
    }

    xioctl(vfd, VIDIOC_STREAMOFF, &type);
    for (unsigned i=0;i<req.count && i<NBUF;i++) if (bufs[i].ptr) munmap(bufs[i].ptr, bufs[i].len);
    close(lfd); close(vfd);
    return bests < 0 ? 1 : 0;
}
