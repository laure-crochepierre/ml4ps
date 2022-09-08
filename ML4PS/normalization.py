import os
import pickle

from scipy import interpolate
import numpy as np
from tqdm import tqdm

from ML4PS.backend.interface import get_backend
from ML4PS.backend.pypowsybl import Backend
from ML4PS.backend.pandapower import Backend


class Normalizer:
    """Normalizes power grid features while respecting the permutation equivariance of the data.

    Attributes:
        functions (:obj:`dict` of :obj:`dict` of :obj:`normalizing_function`): Dict of dict of normalizing functions.
            Upper level keys correspond to objects (e.g. 'load'), lower level keys correspond to features (e.g. 'p_mw')
            and the value corresponds to a normalizing function. Normalizing functions take scalar inputs and return
            scalar inputs.
    """

    def __init__(self, filename=None, **kwargs):
        """Inits Normalizer.

        Args:
            filename (:obj:`str`): Path to a normalizer that should be loaded. If not specified, a new normalizer is
                created based on the other arguments
            backend_name (:obj:`str`): Name of the backend to use to extract features. For now, it can be either
                `pandapower` or `pypowsybl`. Changing the backend will affect the objects and features names.
            data_dir (:obj:`str`): Path to the dataset that will serve to fit the normalizing functions.
            amount_of_samples (:obj:`int`): Amount of samples that should be imported from the dataset to fit the
                normalizing functions. As a matter of fact, fitting normalizing functions on a small subset of the
                dataset is faster, and usually provides a relevant normalization.
            shuffle (:obj:`bool`): If true, samples used to fit the normalizing functions are drawn randomly from the
                dataset. If false, only the first samples in alphabetical order are used.
            break_points (:obj:`int`): Amount of breakpoints that the piecewise linear functions should have. Indeed,
                in the case of multiple data quantiles being equal, the actual amount of breakpoints will be lower.
            features (:obj:`dict` of :obj:`list` of :obj:`str`): Dict of list of feature names. Keys correspond to
                objects (e.g. 'load'), and values are lists of features that should be normalized (e.g. ['p_mw',
                'q_mvar']).
        """
        self.functions = {}

        if filename is not None:
            self.load(filename)
        else:
            self.backend_name = kwargs.get("backend_name", 'pypowsybl')
            self.backend = get_backend(self.backend_name)
            self.data_dir = kwargs.get("data_dir", None)
            self.amount_of_samples = kwargs.get('amount_of_samples', 100)
            self.shuffle = kwargs.get("shuffle", False)
            self.break_points = kwargs.get('break_points', 200)
            self.features = kwargs.get("features", self.backend.valid_features)
            self.backend.check_features(self.features)

            self.build_functions()

    def build_functions(self):
        """"""
        dict_of_all_values = self.get_all_values()
        self.functions = {}
        for k in self.features.keys():
            self.functions[k] = {}
            for f in self.features[k]:
                self.functions[k][f] = self.build_single_function(dict_of_all_values[k][f])

    def get_all_values(self):
        data_files = self.get_data_files()
        values_dict = {k: {f: [] for f in f_list} for k, f_list in self.features.items()}
        for file in tqdm(data_files, desc='Loading all the dataset'):
            net = self.backend.load_network(file)
            for k in self.features.keys():
                table = self.backend.get_table(net, k)
                for f in self.features[k]:
                    if (f in table.keys()) and (not table.empty):
                        values_dict[k][f].append(table[f].to_numpy().flatten().astype(float))
        return values_dict

    def get_data_files(self):
        all_data_files = []
        train_dir = os.path.join(self.data_dir, 'train')
        for f in sorted(os.listdir(train_dir)):
            if f.endswith(self.backend.valid_extensions):
                all_data_files.append(os.path.join(train_dir, f))

        if not all_data_files:
            raise FileNotFoundError("There is no valid file in {}".format(train_dir))

        if self.shuffle:
            np.random.shuffle(all_data_files)

        return all_data_files[:self.amount_of_samples]


    def build_single_function(self, values):
        if values:
            v, p = self.get_quantiles(values)
            v_unique, p_unique = self.merge_equal_quantiles(v, p)
            if len(v_unique) == 1:
                return SubtractFunction(v_unique[0])
            else:
                return interpolate.interp1d(v_unique, -1 + 2 * p_unique, fill_value="extrapolate")
        else:
            return None

    def get_quantiles(self, values):
        """"""
        p = np.arange(0, 1, 1. / self.break_points)
        v = np.quantile(values, p)
        return v, p

    def merge_equal_quantiles(self, v, p):
        v_unique, inverse, counts = np.unique(v, return_inverse=True, return_counts=True)
        p_unique = 0. * v_unique
        np.add.at(p_unique, inverse, p)
        p_unique = p_unique / counts
        return v_unique, p_unique

    def save(self, filename):
        """Saves a normalizer."""
        file = open(filename, 'wb')
        file.write(pickle.dumps(self.functions))
        file.close()

    def load(self, filename):
        """Loads a normalizer."""
        file = open(filename, 'rb')
        self.functions = pickle.loads(file.read())
        file.close()

    def __call__(self, x):
        """Normalizes input data."""
        x_norm = {}
        for k in x.keys():
            if k in self.functions.keys():
                x_norm[k] = {}
                for f in x[k].keys():
                    if (f in self.functions[k].keys()) and (self.functions[k][f] is not None):
                        x_norm[k][f] = self.functions[k][f](x[k][f])
                    else:
                        x_norm[k][f] = x[k][f]
            else:
                x_norm[k] = x[k]
        return x_norm


class SubtractFunction:
    """Class of savable functions that subtract a constant value."""

    def __init__(self, v):
        self.v = v

    def __call__(self, x):
        return x - self.v
