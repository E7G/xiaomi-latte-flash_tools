#include <errno.h>
#include <fcntl.h>
#include <linux/videodev2.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

#define VIDEO_DEV "/dev/video0"
#define OTP_DEV "/sys/bus/nvmem/devices/mipad2-t4ka3-otp/nvmem"
#define STATE_FILE "/run/mipad2-camera-af.env"
#define OTP_SIZE 578
#define FALLBACK_INF 237
#define FALLBACK_MACRO 366
#define NBUF 4
#define MAX_POINTS 256

struct buf { void *p; size_t len; };
struct point { int f; double s1, s2; };

static int xioctl(int fd, unsigned long req, void *arg) {
    int r;
    do r = ioctl(fd, req, arg); while (r < 0 && errno == EINTR);
    return r;
}
static void die(const char *s) { perror(s); exit(1); }

static int read_otp_range(int *inf, int *macro) {
    uint8_t d[OTP_SIZE];
    int fd = open(OTP_DEV, O_RDONLY | O_CLOEXEC);
    if (fd < 0) return -1;

    ssize_t got = 0;
    while (got < OTP_SIZE) {
        ssize_t n = read(fd, d + got, OTP_SIZE - got);
        if (n <= 0) { close(fd); return -1; }
        got += n;
    }
    close(fd);

    if (d[0x10] != 1) return -1;
    unsigned sum = 0;
    for (int i = 0x11; i <= 0x1e; i++) sum += d[i];
    if ((sum % 255) != d[0x1f]) return -1;

    int a = (d[0x13] << 8) | d[0x14];
    int b = (d[0x15] << 8) | d[0x16];
    if (a < 0 || b > 1023 || a >= b) return -1;
    *inf = a; *macro = b;
    return 0;
}

static int read_state_range(int *inf, int *macro) {
    FILE *fp = fopen(STATE_FILE, "r");
    if (!fp) return -1;

    char line[128];
    int a = -1, b = -1;
    while (fgets(line, sizeof(line), fp)) {
        if (sscanf(line, "MIPAD2_AF_INFINITY=%d", &a) == 1) continue;
        if (sscanf(line, "MIPAD2_AF_MACRO=%d", &b) == 1) continue;
    }
    fclose(fp);

    if (a < 0 || b > 1023 || a >= b) return -1;
    *inf = a; *macro = b;
    return 0;
}

static int find_focus_device(char *path, size_t npath) {
    for (int i = 0; i < 32; i++) {
        char p[64];
        snprintf(p, sizeof(p), "/dev/v4l-subdev%d", i);
        int fd = open(p, O_RDWR | O_CLOEXEC);
        if (fd < 0) continue;
        struct v4l2_queryctrl q = { .id = V4L2_CID_FOCUS_ABSOLUTE };
        if (xioctl(fd, VIDIOC_QUERYCTRL, &q) == 0 && !(q.flags & V4L2_CTRL_FLAG_DISABLED)) {
            snprintf(path, npath, "%s", p);
            return fd;
        }
        close(fd);
    }
    errno = ENODEV;
    return -1;
}

static void set_focus(int fd, int value) {
    struct v4l2_control c = { .id = V4L2_CID_FOCUS_ABSOLUTE, .value = value };
    if (xioctl(fd, VIDIOC_S_CTRL, &c) < 0) die("VIDIOC_S_CTRL focus");
}
static int find_rear_input(int vfd) {
    for (unsigned i = 0; i < 32; i++) {
        struct v4l2_input in = { .index = i };
        if (xioctl(vfd, VIDIOC_ENUMINPUT, &in) < 0) {
            if (errno == EINVAL)
                break;
            die("VIDIOC_ENUMINPUT");
        }
        if (strstr((const char *)in.name, "t4ka3"))
            return (int)i;
    }
    errno = ENODEV;
    return -1;
}
static void wait_focus(int from, int to) {
    int d = abs(to - from);
    int us = 30000 + d * 1000;
    if (us > 180000) us = 180000;
    usleep(us);
}
static unsigned char *dq(int vfd, struct buf *b, struct v4l2_buffer *vb) {
    memset(vb, 0, sizeof(*vb));
    vb->type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    vb->memory = V4L2_MEMORY_MMAP;
    if (xioctl(vfd, VIDIOC_DQBUF, vb) < 0) die("VIDIOC_DQBUF");
    if (vb->index >= NBUF) { fprintf(stderr, "bad buffer index\n"); exit(1); }
    return b[vb->index].p;
}
static void qbuf(int vfd, struct v4l2_buffer *vb) {
    if (xioctl(vfd, VIDIOC_QBUF, vb) < 0) die("VIDIOC_QBUF");
}
static void discard_frames(int vfd, struct buf *b, int n) {
    for (int i = 0; i < n; i++) {
        struct v4l2_buffer vb;
        dq(vfd, b, &vb);
        qbuf(vfd, &vb);
    }
}
static double frame_score(const uint8_t *y, int w, int h, int stride) {
    int x0 = w / 6, x1 = w - w / 6, y0 = h / 6, y1 = h - h / 6;
    double edge = 0.0, lum = 0.0;
    uint64_t count = 0;

    for (int yy = y0 + 2; yy < y1 - 2; yy += 2) {
        const uint8_t *up = y + (yy - 1) * stride;
        const uint8_t *row = y + yy * stride;
        const uint8_t *dn = y + (yy + 1) * stride;
        for (int x = x0 + 2; x < x1 - 2; x += 2) {
            int c = row[x];
            edge += abs(2 * c - row[x - 1] - row[x + 1]);
            edge += abs(2 * c - up[x] - dn[x]);
            lum += c + 16.0;
            count++;
        }
    }
    return (!count || lum <= 0.0) ? 0.0 : edge / lum;
}
static int cmpd(const void *a, const void *b) {
    double x = *(const double *)a, y = *(const double *)b;
    return (x > y) - (x < y);
}
static double stable_score(int vfd, struct buf *b, int w, int h, int stride) {
    discard_frames(vfd, b, 3);
    double s[3];
    for (int i = 0; i < 3; i++) {
        struct v4l2_buffer vb;
        uint8_t *p = dq(vfd, b, &vb);
        s[i] = frame_score(p, w, h, stride);
        qbuf(vfd, &vb);
    }
    qsort(s, 3, sizeof(double), cmpd);
    return s[1];
}
static int build_points(struct point *p, int lo, int hi, int step) {
    int n = 0;
    for (int f = lo; f <= hi && n < MAX_POINTS; f += step)
        p[n++] = (struct point){ .f = f };
    if (n && p[n - 1].f != hi && n < MAX_POINTS)
        p[n++] = (struct point){ .f = hi };
    return n;
}
static int scan_pass(int vfd, int ffd, struct buf *b, int w, int h, int stride,
                     struct point *p, int n, int reverse, int current) {
    if (!reverse) {
        for (int i = 0; i < n; i++) {
            set_focus(ffd, p[i].f);
            wait_focus(current, p[i].f);
            current = p[i].f;
            p[i].s1 = stable_score(vfd, b, w, h, stride);
            printf("forward focus=%d score=%.8f\n", p[i].f, p[i].s1);
            fflush(stdout);
        }
    } else {
        for (int i = n - 1; i >= 0; i--) {
            set_focus(ffd, p[i].f);
            wait_focus(current, p[i].f);
            current = p[i].f;
            p[i].s2 = stable_score(vfd, b, w, h, stride);
            printf("reverse focus=%d score=%.8f\n", p[i].f, p[i].s2);
            fflush(stdout);
        }
    }
    return current;
}
static int best_point(struct point *p, int n, double *out) {
    int bi = 0;
    double best = -1.0;
    for (int i = 0; i < n; i++) {
        double s = (p[i].s1 + p[i].s2) / 2.0;
        printf("combined focus=%d score=%.8f\n", p[i].f, s);
        if (s > best) { best = s; bi = i; }
    }
    *out = best;
    return bi;
}

int main(int argc, char **argv) {
    int lo = FALLBACK_INF, hi = FALLBACK_MACRO;
    int fast = 0;
    int argi = 1;
    const char *range_src = "fallback";

    if (argc > 1 && strcmp(argv[1], "--fast") == 0) {
        fast = 1;
        argi++;
    } else if (argc > 1 && strcmp(argv[1], "--full") == 0) {
        argi++;
    } else if (argc > 1 && (strcmp(argv[1], "-h") == 0 ||
                            strcmp(argv[1], "--help") == 0)) {
        fprintf(stderr, "Usage: %s [--fast|--full] [focus-min focus-max]\n", argv[0]);
        return 0;
    }

    if (read_otp_range(&lo, &hi) == 0)
        range_src = "OTP";
    else if (read_state_range(&lo, &hi) == 0)
        range_src = "state";

    if (argc - argi == 2) {
        lo = atoi(argv[argi]);
        hi = atoi(argv[argi + 1]);
        range_src = "override";
    } else if (argc != argi) {
        fprintf(stderr, "Usage: %s [--fast|--full] [focus-min focus-max]\n", argv[0]);
        return 2;
    }
    if (lo < 0 || hi > 1023 || lo >= hi) {
        fprintf(stderr, "invalid focus range %d..%d\n", lo, hi);
        return 2;
    }

    char focus_path[64];
    int ffd = find_focus_device(focus_path, sizeof(focus_path));
    if (ffd < 0) die("find focus device");

    int vfd = open(VIDEO_DEV, O_RDWR | O_CLOEXEC);
    if (vfd < 0) die("open video");
    int input = find_rear_input(vfd);
    if (input < 0) die("find T4KA3 input");
    if (xioctl(vfd, VIDIOC_S_INPUT, &input) < 0) die("VIDIOC_S_INPUT");

    struct v4l2_format fmt = {0};
    fmt.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    fmt.fmt.pix.width = 1280;
    fmt.fmt.pix.height = 720;
    fmt.fmt.pix.pixelformat = V4L2_PIX_FMT_YUV420;
    fmt.fmt.pix.field = V4L2_FIELD_NONE;
    if (xioctl(vfd, VIDIOC_S_FMT, &fmt) < 0) die("VIDIOC_S_FMT");
    if (xioctl(vfd, VIDIOC_G_FMT, &fmt) < 0) die("VIDIOC_G_FMT");
    int w = fmt.fmt.pix.width, h = fmt.fmt.pix.height, stride = fmt.fmt.pix.bytesperline;
    if (fmt.fmt.pix.pixelformat != V4L2_PIX_FMT_YUV420) {
        fprintf(stderr, "unsupported fourcc 0x%08x\n", fmt.fmt.pix.pixelformat);
        return 3;
    }
    fprintf(stderr, "video=%s input=%d(T4KA3) format=%dx%d stride=%d focus=%s range=%d..%d (%s) mode=%s\n",
            VIDEO_DEV, input, w, h, stride, focus_path, lo, hi, range_src,
            fast ? "fast" : "full");

    struct v4l2_requestbuffers req = {0};
    req.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    req.memory = V4L2_MEMORY_MMAP;
    req.count = NBUF;
    if (xioctl(vfd, VIDIOC_REQBUFS, &req) < 0) die("VIDIOC_REQBUFS");
    if (req.count < NBUF) { fprintf(stderr, "not enough buffers\n"); return 4; }

    struct buf b[NBUF] = {0};
    for (unsigned i = 0; i < NBUF; i++) {
        struct v4l2_buffer vb = {0};
        vb.type = req.type; vb.memory = req.memory; vb.index = i;
        if (xioctl(vfd, VIDIOC_QUERYBUF, &vb) < 0) die("VIDIOC_QUERYBUF");
        b[i].len = vb.length;
        b[i].p = mmap(NULL, vb.length, PROT_READ | PROT_WRITE, MAP_SHARED, vfd, vb.m.offset);
        if (b[i].p == MAP_FAILED) die("mmap");
        if (xioctl(vfd, VIDIOC_QBUF, &vb) < 0) die("VIDIOC_QBUF init");
    }

    enum v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    if (xioctl(vfd, VIDIOC_STREAMON, &type) < 0) die("VIDIOC_STREAMON");

    int current = (lo + hi) / 2;
    set_focus(ffd, current);
    wait_focus(lo, current);
    discard_frames(vfd, b, 12);

    struct point coarse[MAX_POINTS];
    int step = (hi - lo) / (fast ? 8 : 16);
    if (step < (fast ? 8 : 6)) step = fast ? 8 : 6;
    int n = build_points(coarse, lo, hi, step);
    current = scan_pass(vfd, ffd, b, w, h, stride, coarse, n, 0, current);
    if (fast) {
        for (int i = 0; i < n; i++)
            coarse[i].s2 = coarse[i].s1;
    } else {
        current = scan_pass(vfd, ffd, b, w, h, stride, coarse, n, 1, current);
    }
    double coarse_score;
    int ci = best_point(coarse, n, &coarse_score);
    int center = coarse[ci].f;

    int rlo = center - step;
    int rhi = center + step;
    if (rlo < lo) rlo = lo;
    if (rhi > hi) rhi = hi;
    struct point fine[MAX_POINTS];
    int fine_step = fast ? 4 : 2;
    int fn = build_points(fine, rlo, rhi, fine_step);
    current = scan_pass(vfd, ffd, b, w, h, stride, fine, fn, 0, current);
    if (fast) {
        for (int i = 0; i < fn; i++)
            fine[i].s2 = fine[i].s1;
    } else {
        current = scan_pass(vfd, ffd, b, w, h, stride, fine, fn, 1, current);
    }
    double fine_score;
    int fi = best_point(fine, fn, &fine_score);
    int best = fine[fi].f;

    set_focus(ffd, best);
    wait_focus(current, best);
    discard_frames(vfd, b, 3);
    printf("BEST focus=%d score=%.8f coarse=%d coarse_score=%.8f range=%d..%d source=%s\n",
           best, fine_score, center, coarse_score, lo, hi, range_src);

    xioctl(vfd, VIDIOC_STREAMOFF, &type);
    close(ffd);
    for (int i = 0; i < NBUF; i++) munmap(b[i].p, b[i].len);
    close(vfd);
    return 0;
}
