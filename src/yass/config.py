from os import path
from collections import Mapping, MutableSequence
import keyword
import logging

import yaml
import numpy as np

from . import geometry as geom


class FrozenJSON(object):
    """A facade for navigating a JSON-like object
    using attribute notation. Based on FrozenJSON from 'Fluent Python'
    """
    @classmethod
    def from_yaml(cls, path_to_file):
        # load config file
        with open(path_to_file) as f:
            mapping = yaml.load(f)

        obj = cls(mapping)

        # save path for reference, helps debugging
        obj._path_to_file = path_to_file

        return obj

    def __new__(cls, arg):
        if isinstance(arg, Mapping):
            return super(FrozenJSON, cls).__new__(cls)

        elif isinstance(arg, MutableSequence):
            return [cls(item) for item in arg]
        else:
            return arg

    def __init__(self, mapping):
        self._logger = logging.getLogger(__name__)
        self._logger.debug('Loaded with params: {}'.format(mapping))

        # set a value of None in _path_to_file if the property has not been
        # set, this means the object was initialized directly (as opposed
        # to using the from_yaml method, so no file was used)
        self._path_to_file = (self._path_to_file if
                              hasattr(self, '_path_to_file') else None)

        self._logger.debug('Loaded from file: {}, path: {}'
                           .format(self._path_to_file is not None,
                                   self._path_to_file if self._path_to_file
                                   else 'Not loaded from file'))

        self._data = {}

        for key, value in mapping.items():

            if keyword.iskeyword(key):
                key += '_'

            self._data[key] = value

    def __getattr__(self, name):
        if hasattr(self._data, name):
            return getattr(self._data, name)
        else:
            return FrozenJSON(self._data[name])

    def __dir__(self):
        return self._data.keys()

    def __getitem__(self, key):
        value = self._data.get(key)

        if value is None:
            raise ValueError('No value was set in Config{}for key "{}", '
                             'available keys are: {}'
                             .format(self._path_to_file, key,
                                     self._data.keys()))

        return value


class Config(FrozenJSON):
    """
    A configuration object for the package, it is a read-only FrozenJSON that
    inits from a yaml file with some caching capbilities to avoid
    redundant and common computations

    Notes
    -----
    After initialization, attributes cannot be changed
    """
    def __init__(self, mapping):
        super(Config, self).__init__(mapping)

        self._logger = logging.getLogger(__name__)

        # init the rest of the parameters, these parameters are used
        # througout the pipeline so we compute them once to avoid redudant
        # computations

        # GEOMETRY PARAMETERS
        path_to_geom = path.join(self.root, self.geomFile)
        self._set_param('geom', geom.parse(path_to_geom, self.nChan))

        neighChannels = geom.find_channel_neighbors(self.geom,
                                                    self.spatialRadius)
        self._set_param('neighChannels', neighChannels)

        channelGroups = geom.make_channel_groups(self.nChan,
                                                 self.neighChannels,
                                                 self.geom)
        self._set_param('channelGroups', channelGroups)

        self._logger.debug('Geometry parameters. Geom: {}, neighChannels: '
                           '{}, channelGroups {}'
                           .format(self.geom, self.neighChannels,
                                   self.channelGroups))

        # FIXME: REMOVE BATCH RELATED BELOW.
        # THIS IS NOW DONE IN BATCH PROCESSOR

        # BUFFER/SPIKE SIZE PARAMETERS
        # compute spikeSize which is the number of observations for half
        # the waveform
        self._set_param('spikeSize',
                        int(np.round(self.spikeSizeMS*self.srate/(2*1000))))
        self._set_param('scaleToSave', 100)
        self._set_param('BUFF', self.spikeSize*4)
        self._set_param('templatesMaxShift', int(self.srate/1000))
        self._set_param('stdFactor', 4)

        file_size = path.getsize(path.join(self.root, self.filename))
        # seems unused...
        self._set_param('size', int(file_size/(sizeof(self.dtype)*self.nChan)))

        # BATCH PARAMETERS
        self._set_param('dsize', sizeof(self.dtype))

        batch_size = int(np.floor(self.maxMem/(self.nChan*self.dsize)))

        if batch_size > self.size:
            self._set_param('nBatches', 1)
            self._set_param('batch_size', self.size)
            self._set_param('residual', 0)
            self._set_param('nPortion', 1)
        else:
            nBatches = int(np.ceil(float(self.size)/batch_size))
            self._set_param('nBatches', nBatches)
            self._set_param('batch_size', batch_size)
            self._set_param('residual', self.size % batch_size)
            self._set_param('nPortion', np.ceil(self.partialDat*self.nBatches))

        self._logger.debug('Computed params: spikeSize: {}, scaleToSave: {}, '
                           'BUFF: {}, templatesMaxShift: {}, stdFactor: {}, '
                           'size: {}, dsize: {}, nBatches: {}, batch_size: {}'
                           ', residual: {}, nPortion: {}'
                           .format(self.spikeSize, self.scaleToSave,
                                   self.BUFF, self.templatesMaxShift,
                                   self.stdFactor, self.size,
                                   self.dsize, self.nBatches,
                                   self.batch_size, self.residual,
                                   self.nPortion))

    def __setattr__(self, name, value):
        if not name.startswith('_'):
            raise AttributeError('Cannot set values once the object has '
                                 'been initialized')
        else:
            self.__dict__[name] = value

    def _set_param(self, name, value):
        """
        Internal setattr method to set new parameters, only used to fill the
        parameters that need to be computed *right after* initialization
        """
        self._data[name] = value


def sizeof(dtype):
    SIZE_ = {'int16': 2,
             'uint16': 2,
             'single': 4,
             'double': 8}
    return SIZE_[dtype]
