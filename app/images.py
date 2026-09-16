"""Local input normalization. No image or metadata is sent to a conversion service."""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

MAX_INPUT_BYTES = 50 * 1024 * 1024
MAX_IMAGE_BYTES = 12 * 1024 * 1024


def normalize_image(raw, filename):
    name=Path(filename or '题目图片').name[:150]
    if len(raw)>MAX_INPUT_BYTES:
        raise ValueError(f'{name}：文件为 {len(raw)/1024/1024:.1f} MB，上传上限为 50 MB，请先缩小图片。')
    mime=None
    if raw.startswith(b'\x89PNG\r\n\x1a\n'): mime='image/png'
    elif raw.startswith(b'\xff\xd8\xff'): mime='image/jpeg'
    elif raw[:4]==b'RIFF' and raw[8:12]==b'WEBP': mime='image/webp'
    heic=raw[4:8]==b'ftyp' and any(brand in raw[8:64] for brand in (b'heic',b'heix',b'hevc',b'hevx',b'mif1',b'msf1'))
    if not mime and not heic:
        raise ValueError(f'{name}：无法识别图片格式，请使用 HEIC、JPEG、PNG 或 WebP。')
    if mime and len(raw)<=MAX_IMAGE_BYTES:
        return raw,mime,name
    if sys.platform!='darwin':
        raise ValueError(f'{name}：当前系统没有本机 HEIC/大图转换器，请先导出为小于 12 MB 的 JPEG。')
    with tempfile.TemporaryDirectory(prefix='power-image-') as directory:
        source=Path(directory)/('input.heic' if heic else 'input.image')
        output=Path(directory)/'converted.jpg'
        source.write_bytes(raw)
        try:
            details=subprocess.run(['/usr/bin/sips','-g','pixelWidth','-g','pixelHeight',str(source)],
                                   capture_output=True,check=True,timeout=30).stdout.decode()
            dimensions=[int(v) for v in re.findall(r'pixel(?:Width|Height):\s*(\d+)',details)]
            if len(dimensions)!=2 or dimensions[0]*dimensions[1]>80_000_000:
                raise ValueError(f'{name}：图片尺寸异常或超过 8000 万像素，请先缩小图片。')
            subprocess.run(['/usr/bin/sips','-s','format','jpeg','-s','formatOptions','85','-Z','3200',
                            str(source),'--out',str(output)],capture_output=True,check=True,timeout=45)
            data=output.read_bytes()
        except (OSError,subprocess.SubprocessError):
            raise ValueError(f'{name}：本机图片转换失败，请从照片或预览中导出为 JPEG 后重试。') from None
    if not data.startswith(b'\xff\xd8\xff') or len(data)>MAX_IMAGE_BYTES:
        raise ValueError(f'{name}：转换后仍超过 12 MB 或格式无效，请先裁剪题目区域。')
    return data,'image/jpeg',Path(name).stem+'.jpg'
