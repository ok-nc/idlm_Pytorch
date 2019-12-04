USE_LORENTZ = False
LINEAR = [8, 50, 500, 1000, 1000, 1000, 500, 150]
CONV_OUT_CHANNEL = [4, 4, 4]
CONV_KERNEL_SIZE = [8, 5, 5]
CONV_STRIDE = [2, 1, 1]
REG_SCALE = 5e-7
BATCH_SIZE = 128
BACK_PROP_BATCH_SIZE = 4096
EVAL_STEP = 1000
TRAIN_STEP = 2
LEARN_RATE = 1e-2
# DECAY_STEP = 25000 # This is for step decay, however we are using dynamic decaying
LR_DECAY_RATE = 0.5
X_RANGE = [i for i in range(2, 10 )]
Y_RANGE = [i for i in range(10 , 2011 )]
# TRAIN_FILE = 'bp2_OutMod.csv'
# VALID_FILE = 'bp2_OutMod.csv'
STOP_THRESHOLD = 1e-3
FORCE_RUN = True
MODEL_NAME  = ''
DATA_DIR = '../'
GEOBOUNDARY =[30, 52, 42, 52]
NORMALIZE_INPUT = True
DETAIL_TRAIN_LOSS_FORWARD = True
CONV1D_FILTERS = ()     # (160, 20, 5)
CONV_CHANNEL_LIST = ()  # (4,2,1)
WRITE_WEIGHT_STEP = 5000
OPTIM = "Adam"
BACK_PROP_EPOCH = 200
USE_CPU_ONLY = False
EVAL_MODEL = "20191202_161923"