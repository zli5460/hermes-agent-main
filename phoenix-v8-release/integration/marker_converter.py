"""不死鸟 Phoenix V8 — Marker PDF转换
PDF转Markdown神器
"""

from typing import Dict

class MarkerConverter:
    """Marker PDF转Markdown"""
    
    def __init__(self):
        self._available = False
        try:
            import marker
            self._available = True
        except ImportError:
            pass
    
    def is_available(self) -> bool:
        return self._available
    
    def convert(self, pdf_path: str) -> Dict:
        """PDF转Markdown"""
        if not self._available:
            return {"error": "Marker未安装", "markdown": ""}
        
        try:
            from marker.converters.pdf import PdfConverter
            from marker.models import create_model_dict
            
            converter = PdfConverter(artifact_dict=create_model_dict())
            rendered = converter(pdf_path)
            
            return {
                "markdown": rendered.markdown[:20000],
                "metadata": rendered.metadata if hasattr(rendered, 'metadata') else {},
                "status": 200,
            }
        except Exception as e:
            return {"error": str(e), "markdown": "", "status": 0}

marker_converter = MarkerConverter()
