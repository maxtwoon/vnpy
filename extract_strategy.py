"""
Step 1: 解压并读取策略zip文件内容
运行方式: python extract_strategy.py
"""
import zipfile
import os
import glob

# 搜索uploads目录下的zip文件
uploads_dir = r"C:\Users\Admin\AppData\Roaming\Claude\local-agent-mode-sessions\8efeee83-efd6-4dc3-9723-d1251b26e40d\c12cb3c6-c48b-487c-8c74-b2ae7fc63440\local_a2ceb028-be8d-475f-95c0-e41b52dac1c0\uploads"

zip_files = glob.glob(os.path.join(uploads_dir, "*.zip"))
print(f"找到zip文件: {zip_files}")

if not zip_files:
    print("未找到zip文件！")
    exit(1)

zip_path = zip_files[0]
print(f"使用zip文件: {zip_path}")

# 输出目录
extract_dir = r"D:\repo\vnpy\strategy_source"
os.makedirs(extract_dir, exist_ok=True)

# 解压
with zipfile.ZipFile(zip_path, 'r') as z:
    file_list = z.infolist()
    print(f"\nZIP内容（共{len(file_list)}个文件）：")
    for info in file_list:
        print(f"  {info.filename} ({info.file_size} bytes)")

    z.extractall(extract_dir)
    print(f"\n已解压到: {extract_dir}")

# 读取所有文本文件内容并汇总
output_file = r"D:\repo\vnpy\strategy_content.txt"
with open(output_file, 'w', encoding='utf-8') as out:
    for root, dirs, files in os.walk(extract_dir):
        for fname in files:
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, extract_dir)
            out.write(f"\n{'='*60}\n")
            out.write(f"文件: {rel}\n")
            out.write(f"{'='*60}\n")
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    content = f.read()
                out.write(content)
                print(f"已读取: {rel} ({len(content)} 字符)")
            except UnicodeDecodeError:
                try:
                    with open(fpath, 'r', encoding='gbk') as f:
                        content = f.read()
                    out.write(content)
                    print(f"已读取(GBK): {rel}")
                except Exception as e:
                    out.write(f"[二进制文件或读取失败: {e}]\n")
                    print(f"跳过二进制文件: {rel}")

print(f"\n✅ 策略内容已汇总到: {output_file}")
print("请查看 strategy_content.txt 了解策略详情")
