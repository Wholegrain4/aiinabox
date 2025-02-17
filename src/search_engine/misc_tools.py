import chardet
import re
class MiscTools:
    """Misc tools for the software platform"""
    def __init__(self):
        pass
    def detect_encoding(self, file_path):
        with open(file_path, "rb") as f:
            result = chardet.detect(f.read())
        return result["encoding"]
    
    def sanitize_filename(self, title):
        # Remove or replace invalid characters
        return re.sub(r'[\\/*?:"<>|]', "", title)
    

