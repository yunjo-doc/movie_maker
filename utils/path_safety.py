"""영문 임시 디렉토리에서 작업하여 한글 경로 문제 회피"""

import tempfile
import shutil
from pathlib import Path


class SafeWorkDir:
    def __init__(self):
        self.work_dir = None

    def create(self) -> str:
        self.work_dir = tempfile.mkdtemp(prefix="vid_")
        return self.work_dir

    def copy_to_work(self, src: str, filename: str = None) -> str:
        fname = filename or Path(src).name
        # 비ASCII 문자 제거하여 안전한 파일명 생성
        safe_name = "".join(c if c.isascii() and c not in '<>:"/\\|?*' else "_" for c in fname)
        if not safe_name:
            safe_name = f"file_{abs(hash(fname))}"
        dst = Path(self.work_dir) / safe_name
        shutil.copy2(src, dst)
        return str(dst)

    def cleanup(self):
        if self.work_dir and Path(self.work_dir).exists():
            shutil.rmtree(self.work_dir, ignore_errors=True)
