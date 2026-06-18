# [2026-06-18] 新增：scripts 包初始化测试

def test_scripts_package_importable():
    """scripts 包应有 __init__.py，可被 import"""
    import scripts
    assert scripts is not None
