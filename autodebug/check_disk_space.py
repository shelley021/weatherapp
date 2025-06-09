import subprocess
import sys

def check_disk_space():
    """检查 GitHub Actions 运行环境的磁盘空间"""
    try:
        # 检查磁盘使用情况
        df_result = subprocess.run(["df", "-h"], capture_output=True, text=True, check=True)
        print("磁盘使用情况：")
        print(df_result.stdout)

        # 检查 /tmp 目录的使用情况
        du_result = subprocess.run(
            ["du", "-h", "/tmp", "-d", "1", "--no-dereference"],
            capture_output=True, text=True, check=False
        )
        if du_result.returncode == 0:
            print("/tmp 目录使用情况：")
            print(du_result.stdout)
        else:
            print("无法检查 /tmp 目录：", du_result.stderr)

        # 检查可用空间是否低于 500 MB
        df_lines = df_result.stdout.splitlines()
        for line in df_lines:
            if "/home/runner" in line:
                available_space = line.split()[3]  # 可用空间（格式如 "2.5G"）
                unit = available_space[-1]  # 单位（G, M 等）
                space = float(available_space[:-1])  # 数值部分
                if unit == "G" and space < 0.5:
                    print(f"警告：可用空间不足 500 MB，仅剩 {available_space}")
                    return False
                elif unit == "M" and space < 500:
                    print(f"警告：可用空间不足 500 MB，仅剩 {available_space}")
                    return False
                print(f"可用空间充足：{available_space}")
                return True
        print("未找到 /home/runner 的磁盘信息")
        return False

    except subprocess.CalledProcessError as e:
        print(f"错误：无法检查磁盘空间 - {e}")
        return False
    except Exception as e:
        print(f"错误：{e}")
        return False

if __name__ == "__main__":
    if not check_disk_space():
        sys.exit(1)