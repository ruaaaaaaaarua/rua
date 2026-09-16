import sys
from pathlib import Path
import pytest

from app.images import normalize_image


def test_rejects_invalid_file_with_its_name():
    with pytest.raises(ValueError, match='broken.heic'):
        normalize_image(b'not an image', 'broken.heic')


def test_preserves_supported_small_image():
    raw=b'\x89PNG\r\n\x1a\nfixture'
    data,mime,name=normalize_image(raw,'question.png')
    assert data==raw and mime=='image/png' and name=='question.png'


@pytest.mark.skipif(sys.platform!='darwin',reason='macOS native HEIC conversion')
def test_actual_user_heic_converts_locally_without_changing_original():
    path=Path('/Users/ruaaaaaaaa/Downloads/IMG_1430.HEIC')
    if not path.exists():
        pytest.skip('user image is not part of the repository')
    raw=path.read_bytes()
    data,mime,name=normalize_image(raw,path.name)
    assert mime=='image/jpeg' and data.startswith(b'\xff\xd8\xff')
    assert len(data)<12*1024*1024 and name=='IMG_1430.jpg'
    assert path.read_bytes()==raw
