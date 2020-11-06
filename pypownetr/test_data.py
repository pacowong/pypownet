import tempfile
from .data import *

def test_pownet_data():
    pn_data = PowerNetDataCambodian('datasets/kamal0013/camb_2016')
    tf = tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".dat")
    pn_data.export_model_data_fp(tf)
    tf.close()
