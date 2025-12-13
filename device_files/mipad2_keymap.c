#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <linux/input.h>
#include <linux/input-event-codes.h>

#define DEVICE_NAME_SIZE 32

// 具体的键位映射表
struct key_mapping
{
    u_int32_t scancode;
    unsigned int keycode;
    const char *desc;
    const char *from;
    const char *to;
};

// 小米平板2键盘的特殊映射
static struct key_mapping mipad2_keymap[] = {
    {0x700e0, KEY_RESERVED, "禁用左Ctrl键", "LeftCtrl", "忽略"},
    {0x700e3, KEY_RESERVED, "禁用左Meta键", "LeftMeta", "忽略"},
    {0x70016, KEY_APPSELECT, "S键变多任务键", "S", "AppSelect"},
    {0x70029, KEY_HOMEPAGE, "Esc键变Home键", "Esc", "Homepage"},
    {0x7002a, KEY_BACK, "退格变返回键", "Backspace", "Back"},
    {0, 0, NULL, NULL, NULL} // 结束标记
};

// 详细的设备信息结构
struct device_info
{
    char name[DEVICE_NAME_SIZE];
    int bustype;
    int vendor;
    int product;
    int version;
};

// 获取设备信息
int get_device_info(int fd, struct device_info *info)
{
    memset(info, 0, sizeof(*info));

    // 获取设备名称
    if (ioctl(fd, EVIOCGNAME(sizeof(info->name)), info->name) < 0)
    {
        printf("获取设备名称失败: %s\n", strerror(errno));
        return -1;
    }

    // 获取设备ID
    struct input_id id;
    if (ioctl(fd, EVIOCGID, &id) == 0)
    {
        info->bustype = id.bustype;
        info->vendor = id.vendor;
        info->product = id.product;
        info->version = id.version;
    }

    return 0;
}

// 检查是否为目标设备
int is_mipad2_keyboard(int fd)
{
    struct device_info info;

    if (get_device_info(fd, &info) < 0)
    {
        return 0;
    }

    // 检查设备名称
    if (strstr(info.name, "FTSC1000:00 2808:509C Keyboard") == NULL)
    {
#ifdef DEBUG
        printf("设备名称不匹配: %s\n", info.name);
#endif
        return 0;
    }

    // 检查设备ID
    if (info.vendor != 0x2808 || info.product != 0x509c)
    {
        return 0;
    }

#ifdef DEBUG
    printf("检测到目标设备:\n");
    printf("  名称: %s\n", info.name);
    printf("  ID: bustype=0x%04x vendor=0x%04x product=0x%04x\n",
           info.bustype, info.vendor, info.product);
#endif

    return 1;
}

// 将扫描码转换为 uint64_t
u_int64_t scancode_to_uint64(const u_int8_t *scancode, u_int8_t len)
{
    if (!scancode || len == 0)
        return 0;

    // 限制最大长度为 8（uint64_t 最大）
    if (len > 8)
        len = 8;

    u_int64_t value = 0;
    for (int i = 0; i < len; i++)
    {
        value |= ((u_int64_t)scancode[i]) << (i * 8);
    }
    return value;
}

// 将扫描码转换为 uint32_t（HID usage code）
static inline u_int32_t scancode_to_uint32(const u_int8_t *scancode)
{
    return (u_int32_t)scancode_to_uint64(scancode, 4);
}

// 如果扫描码在键位映射列表中
int scancode_in_keymap(u_int8_t *scancode, int len)
{
    for (int i = 0; mipad2_keymap[i].scancode != 0; i++)
    {
        if (mipad2_keymap[i].scancode == scancode_to_uint32(scancode))
        {
            return 1;
        }
    }
    return 0;
}

// 如果扫描码在键位映射列表中 u_int32_t
int is_scancode_in_keymap_uint32(u_int8_t *scancode)
{
    return scancode_in_keymap(scancode, 4);
}

// 应用单个键位映射
int apply_keymap_single(int fd, struct input_keymap_entry *ke)
{
    int found = 0;
    for (int i = 0; mipad2_keymap[i].scancode != 0; i++)
    {
        struct key_mapping map = mipad2_keymap[i];

        if (scancode_to_uint32(ke->scancode) == map.scancode)
        {
            ke->keycode = map.keycode;
            if (ioctl(fd, EVIOCSKEYCODE_V2, ke) < 0)
            {
                printf("  ✗ 修改失败 0x%06x (%s → %s): %s\n",
                       scancode_to_uint32(ke->scancode), map.from, map.to, strerror(errno));
                return -1;
            }
            printf("  ✓ 成功 %s: 0x%06x (%s → %s)\n",
                   map.desc, scancode_to_uint32(ke->scancode), map.from, map.to);
            found = 1;
            goto end;
        }
    }
    if (!found)
    {
        return -1;
    }
end:
    return 0;
}

// 应用键位映射
int apply_keymap(int fd)
{
    struct input_keymap_entry ke;
    int ret = -1;

    for (int index = 0;; index++)
    {
        memset(&ke, 0, sizeof(ke));
        ke.index = index;
        ke.len = 4;
        ke.flags = INPUT_KEYMAP_BY_INDEX;

        if (ioctl(fd, EVIOCGKEYCODE_V2, &ke) < 0)
        {
            if (errno == EINVAL)
            {
                break;
            }
            else
            {
                printf("  ✗ 遍历索引 %d 失败: %s\n", index, strerror(errno));
            }
        }

        if (!apply_keymap_single(fd, &ke))
        {
            ret = 0;
        }
    }

    return ret;
}

// 读取当前映射（用于调试）
void dump_current_mappings(int fd)
{
    struct input_keymap_entry ke;

    printf("\n当前键位映射状态:\n");

    for (int index = 0;; index++)
    {
        memset(&ke, 0, sizeof(ke));
        ke.index = index;
        ke.len = 4;
        ke.flags = INPUT_KEYMAP_BY_INDEX;
        int ret = ioctl(fd, EVIOCGKEYCODE_V2, &ke);
        if (ret == 0 && is_scancode_in_keymap_uint32(ke.scancode))
        {
            printf("  扫描码 0x%06x -> 键码 %d\n", scancode_to_uint32(ke.scancode), ke.keycode);
        }
        else if (ret < 0)
        {
            if (errno == EINVAL)
            {
                break;
            }
            else
            {
                printf("  ✗ 遍历索引 %d 失败: %s\n", index, strerror(errno));
            }
        }
    }
}

int get_device_path(char *device_path)
{
    for (int i = 0; i < 32; i++)
    {
        snprintf(device_path, DEVICE_NAME_SIZE, "/dev/input/event%d", i);

        // 尝试打开设备
        int fd = open(device_path, O_RDWR);
        if (fd < 0)
        {
            continue;
        }

        // 验证是否为目标设备
        if (!is_mipad2_keyboard(fd))
        {
            close(fd);
            continue;
        }
        printf("\n找到目标设备: %s\n", device_path);
        close(fd);
        return 1;
    }

    printf("未找到任何小米平板2电容触摸按键设备\n");
    return 0;
}

// 主函数
int main(int argc, char *argv[])
{
    char device_path[DEVICE_NAME_SIZE];

    printf("小米平板2键盘重映射工具\n");

    // 检查root权限
    if (geteuid() != 0)
    {
        printf("错误: 需要root权限运行\n");
        return 1;
    }

    if (argc > 1)
    {
        if (strlen(argv[1]) > DEVICE_NAME_SIZE)
        {
            printf("设备路径过长\n");
            return 2;
        }
        strcpy(device_path, argv[1]);
    }
    else
    {
        // 遍历所有可能的输入设备
        if (!get_device_path(device_path))
        {
            goto error;
        }
    }

    int fd = open(device_path, O_RDWR);
    if (fd < 0)
    {
        printf("设备打开失败: %s\n", strerror(errno));
        goto error;
    }
    if (!is_mipad2_keyboard(fd))
    {
        printf("设备不是小米平板2键盘\n");
        goto error;
    }

    // 显示当前映射状态
    dump_current_mappings(fd);

    printf("\n开始应用重映射:\n");
    printf("================================\n");

    // 应用所有映射
    if (apply_keymap(fd) != 0)
    {
        printf("  ✗ 键位映射应用失败\n");
        goto error;
    }

    printf("================================\n");
    printf("设备 %s 映射完成\n",
           device_path);

    // 显示映射后的状态
    dump_current_mappings(fd);

    close(fd);

    // 提供测试建议
    printf("\n测试建议:\n");
    printf("1. 使用 evtest /dev/input/eventX 测试按键 (X为设备编号)\n");
    char *button_name[] = {NULL, NULL, "menu", "home", "back"};
    for (int i = 2; i < 5; i++)
    {
        printf("%d. 按%s键应该显示 code=%d(%s)\n", i, button_name[i], mipad2_keymap[i].keycode, mipad2_keymap[i].to);
    }

    return 0;

error:
    printf("发生错误，映射未完成\n");
    close(fd);
    return 1;
}
