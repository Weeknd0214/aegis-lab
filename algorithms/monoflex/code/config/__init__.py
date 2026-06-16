from .defaults import _C as cfg

classes = cfg.DATASETS.DETECT_CLASSES
TYPE_ID_CONVERSION = {cls:classes.index(cls) for cls in classes}
