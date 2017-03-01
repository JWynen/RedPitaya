import os
import fcntl
import mmap

import numpy as np

class acq (object):
    # sampling frequency
    FS = 125000000.0
    # linear addition multiplication register width
    DW = 14
    # fixed point range
    DWr  = (1 << (DW -1)) - 1
    # buffer parameters
    N = 2**14 # table size
    # control register masks
    CTL_STO_MASK = np.uint32(1<<3) # 1 - stop/abort; returns 1 when stopped
    CTL_STA_MASK = np.uint32(1<<2) # 1 - start
    CTL_SWT_MASK = np.uint32(1<<1) # 1 - sw trigger bit (sw trigger must be enabled)
    CTL_RST_MASK = np.uint32(1<<0) # 1 - reset state machine so that it is in known state
    # mode register masks
    MOD_AUT_MASK = np.uint32(1<<1)  # automatic
    MOD_CON_MASK = np.uint32(1<<0)  # continuous
    # trigger edge dictionary
    edges = {'positive': 0, 'negative': 1,
             'pos'     : 0, 'neg'     : 1,
             'p'       : 0, 'n'       : 1,
             '+'       : 0, '-'       : 1}
    # analog stage range voltages
    ranges = (1.0, 20.0)
    # filter coeficients
    filters = { 1.0: (0x7D93, 0x437C7, 0xd9999a, 0x2666),
               20.0: (0x4C5F, 0x2F38B, 0xd9999a, 0x2666)}

    regset_dtype = np.dtype([
        # control/status
        ('ctl_sts', 'uint32'),
        ('cfg_mod', 'uint32'),  # mode
        # trigger configuration
        ('cfg_trg', 'uint32'),  # trigger mask
        ('rsv0'   , 'uint32'),  # reserved
        # pre/post trigger counters
        ('cfg_pre', 'uint32'),  # configuration pre  trigger
        ('cfg_pst', 'uint32'),  # configuration post trigger
        ('sts_pre', 'uint32'),  # status pre  trigger
        ('sts_pst', 'uint32'),  # status post trigger
        # timestamp
        ('cts_acq', 'uint32',2),  # start
        ('cts_trg', 'uint32',2),  # trigger
        ('cts_stp', 'uint32',2),  # stop
        ('rsv1'   , 'uint32',2),  # reserved
        # edge detection
        ('cfg_lvl', 'uint32'),  # level
        ('cfg_hst', 'uint32'),  # hysteresis
        ('cfg_edg', 'uint32'),  # edge (0-pos, 1-neg)
        ('cfg_rng', 'uint32'),  # range (not used by HW)

        # decimation
        ('cfg_dec', 'uint32'),  # decimation factor
        ('cfg_shr', 'uint32'),  # shift right
        ('cfg_avg', 'uint32'),  # average enable
        # filter
        ('cfg_byp', 'uint32'),  # bypass
        ('cfg_faa', 'uint32'),  # AA coeficient
        ('cfg_fbb', 'uint32'),  # BB coeficient
        ('cfg_fkk', 'uint32'),  # KK coeficient
        ('cfg_fpp', 'uint32')   # PP coeficient
    ])

    def __init__ (self, index:int, input_range:float, uio:str = '/dev/uio/acq'):
        """Module instance index should be provided"""

        # use index
        uio = uio+str(index)

        # open device file
        try:
            self.uio_dev = os.open(uio, os.O_RDWR | os.O_SYNC)
        except OSError as e:
            raise IOError(e.errno, "Opening {}: {}".format(uio, e.strerror))

        # exclusive lock
        try:
            fcntl.flock(self.uio_dev, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except IOError as e:
            raise IOError(e.errno, "Locking {}: {}".format(uio, e.strerror))

        # map regset
        try:
            self.uio_reg = mmap.mmap(
                fileno=self.uio_dev, length=mmap.PAGESIZE, offset=0x0,
                flags=mmap.MAP_SHARED, prot=(mmap.PROT_READ | mmap.PROT_WRITE))
        except OSError as e:
            raise IOError(e.errno, "Mapping (regset) {}: {}".format(uio, e.strerror))

        regset_array = np.recarray(1, self.regset_dtype, buf=self.uio_reg)
        self.regset = regset_array[0]

        # map buffer table
        try:
            self.uio_tbl = mmap.mmap(
                # TODO: probably the length should be rounded up to mmap.PAGESIZE
                fileno=self.uio_dev, length=4*self.N, offset=mmap.PAGESIZE,
                flags=mmap.MAP_SHARED, prot=(mmap.PROT_READ | mmap.PROT_WRITE))
        except OSError as e:
            raise IOError(e.errno, "Mapping (buffer) {}: {}".format(uio, e.strerror))

        #table_array = np.recarray(1, self.table_dtype, buf=self.uio_tbl)
        self.table = np.frombuffer(self.uio_tbl, 'int32')

        # set input range (there is no default)
        self.input_range = input_range

    def __del__ (self):
        self.uio_tbl.close()
        self.uio_reg.close()
        try:
            os.close(self.uio_dev)
        except OSError as e:
            raise IOError(e.errno, "Closing {}: {}".format(uio, e.strerror))

    def show_regset (self):
        print (
            "ctl_sts = 0x{reg:x} = {reg:d}                              \n".format(reg=self.regset.ctl_sts)+
            "cfg_mod = 0x{reg:x} = {reg:d}  # mode                      \n".format(reg=self.regset.cfg_mod)+
            "cfg_trg = 0x{reg:x} = {reg:d}  # trigger mask              \n".format(reg=self.regset.cfg_trg)+
            "cfg_pre = 0x{reg:x} = {reg:d}  # configuration pre  trigger\n".format(reg=self.regset.cfg_pre)+
            "cfg_pst = 0x{reg:x} = {reg:d}  # configuration post trigger\n".format(reg=self.regset.cfg_pst)+
            "sts_pre = 0x{reg:x} = {reg:d}  # status pre  trigger       \n".format(reg=self.regset.sts_pre)+
            "sts_pst = 0x{reg:x} = {reg:d}  # status post trigger       \n".format(reg=self.regset.sts_pst)+
            "cfg_lvl = 0x{reg:x} = {reg:d}  # level                     \n".format(reg=self.regset.cfg_lvl)+
            "cfg_hst = 0x{reg:x} = {reg:d}  # hysteresis                \n".format(reg=self.regset.cfg_hst)+
            "cfg_edg = 0x{reg:x} = {reg:d}  # edge (0-pos, 1-neg)       \n".format(reg=self.regset.cfg_edg)+
            "cfg_rng = 0x{reg:x} = {reg:d}  # range (not used by HW)    \n".format(reg=self.regset.cfg_rng)+
            "cfg_dec = 0x{reg:x} = {reg:d}  # decimation factor         \n".format(reg=self.regset.cfg_dec)+
            "cfg_shr = 0x{reg:x} = {reg:d}  # shift right               \n".format(reg=self.regset.cfg_shr)+
            "cfg_avg = 0x{reg:x} = {reg:d}  # average enable            \n".format(reg=self.regset.cfg_avg)+
            "cfg_byp = 0x{reg:x} = {reg:d}  # bypass                    \n".format(reg=self.regset.cfg_byp)+
            "cfg_faa = 0x{reg:x} = {reg:d}  # AA coeficient             \n".format(reg=self.regset.cfg_faa)+
            "cfg_fbb = 0x{reg:x} = {reg:d}  # BB coeficient             \n".format(reg=self.regset.cfg_fbb)+
            "cfg_fkk = 0x{reg:x} = {reg:d}  # KK coeficient             \n".format(reg=self.regset.cfg_fkk)+
            "cfg_fpp = 0x{reg:x} = {reg:d}  # PP coeficient             \n".format(reg=self.regset.cfg_fpp)
        )

    @property
    def input_range (self) -> float:
        return (self.__input_range)

    @input_range.setter
    def input_range (self, value: float):
        if value in self.ranges:
            self.__input_range = value
            self.filter_coeficients = self.filters[value]
        else:
            raise ValueError("Input range can be one of {} volts.".format(self.ranges))

    def reset (self):
        """reset state machine"""
        self.regset.ctl_sts = self.CTL_RST_MASK

    def trigger (self):
        """activate SW trigger"""
        self.regset.ctl_sts = self.CTL_SWT_MASK

    def start (self):
        """start acquisition"""
        self.regset.ctl_sts = self.CTL_STA_MASK

    def stop (self):
        """stop acquisition"""
        self.regset.ctl_sts = self.CTL_STO_MASK

    def status (self) -> int:
        """start state machine"""
        return (self.regset.ctl_sts)

    @property
    def trigger_mask (self):
        return (self.regset.cfg_trg)

    @trigger_mask.setter
    def trigger_mask (self, value):
        # TODO check range
        self.regset.cfg_trg = value

    @property
    def continuous (self) -> bool:
        return (bool(self.regset.cfg_mod & self.MOD_CON_MASK))

    @continuous.setter
    def continuous (self, value: bool):
        if value:  self.regset.cfg_mod |=  self.MOD_CON_MASK
        else:      self.regset.cfg_mod &= ~self.MOD_CON_MASK

    @property
    def automatic (self) -> bool:
        return (bool(self.regset.cfg_mod & self.MOD_AUT_MASK))

    @automatic.setter
    def automatic (self, value: bool):
        if value:  self.regset.cfg_mod |=  self.MOD_AUT_MASK
        else:      self.regset.cfg_mod &= ~self.MOD_AUT_MASK

    @property
    def trigger_pre_delay (self) -> int:
        # TODO units should be secconds
        return (self.regset.cfg_pre)

    @trigger_pre_delay.setter
    def trigger_pre_delay (self, value: int):
        # TODO units should be secconds
        # TODO check range
        self.regset.cfg_pre = value

    @property
    def trigger_post_delay (self) -> int:
        # TODO units should be secconds
        return (self.regset.cfg_pst)

    @trigger_post_delay.setter
    def trigger_post_delay (self, value: int):
        # TODO units should be secconds
        # TODO check range
        self.regset.cfg_pst = value

    @property
    def trigger_pre_status (self) -> int:
        # TODO units should be secconds
        return (self.regset.sts_pre)

    @property
    def trigger_post_status (self) -> int:
        # TODO units should be secconds
        return (self.regset.sts_pst)

    @property
    def level (self) -> float:
        """Trigger level in vols"""
        return (self.regset.cfg_lvl / self.DWMr * self.__input_range)

    @level.setter
    def level (self, value: float):
        """Trigger level in vols"""
        if (-1.0 <= value <= 1.0):
            self.regset.cfg_lvl = value / self.__input_range * self.DWr
        else:
            raise ValueError("Trigger level should be inside [{},{}]".format(self.__input_range))

    @property
    def hysteresis (self) -> float:
        """Trigger hysteresis in vols"""
        return (self.regset.cfg_hst / self.DWMr * self.__input_range)

    @hysteresis.setter
    def hysteresis (self, value: float):
        """Trigger hysteresis in vols"""
        if (-1.0 <= value <= 1.0):
            self.regset.cfg_hst = value / self.__input_range * self.DWr
        else:
            raise ValueError("Trigger level should be inside [{},{}]".format(self.__input_range))

    @property
    def edge (self) -> str:
        """Trigger edge as a string 'pos'/'neg'"""
        return (bool(self.regset.cfg_mod & MOD_CON_MASK))

    @edge.setter
    def edge (self, value: str):
        """Trigger edge as a string 'pos'/'neg'"""
        if (value in self.edges):
            self.regset.cfg_edg = self.edges[value]
        else:
            raise ValueError("Trigger edge should be obe of {}".format(list(self.edges.keys())))

    @property
    def decimation (self) -> int:
        return (self.regset.cfg_dec + 1)

    @decimation.setter
    def decimation (self, value: int):
        # TODO check range
        self.regset.cfg_dec = value - 1

    @property
    def average (self) -> bool:
        # TODO units should be secconds
        return (bool(self.regset.cfg_avg))

    @average.setter
    def average (self, value: bool):
        # TODO check range, for non 2**n decimation factors,
        # scaling should be applied in addition to shift
        self.regset.cfg_avg = int(value)
        self.regset.cfg_shr = math.ceil(math.log2(self.decimation))

    @property
    def filter_coeficients (self) -> tuple:
        return (self.regset.cfg_faa,
                self.regset.cfg_fbb,
                self.regset.cfg_fkk,
                self.regset.cfg_fpp)

    @filter_coeficients.setter
    def filter_coeficients (self, value: tuple):
        # TODO check range
        self.regset.cfg_faa = value[0]
        self.regset.cfg_fbb = value[1]
        self.regset.cfg_fkk = value[2]
        self.regset.cfg_fpp = value[3]

    def data(self):
        """Data containing normalized values in the range [-1,1]"""
        siz = self.N
        # TODO: nparray
        return [self.table[i] / self.DWr * self.__input_range for i in range(siz)]
