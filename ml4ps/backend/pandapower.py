from ml4ps.backend.interface import AbstractBackend
from ml4ps.utils import clean_dict, convert_addresses_to_integers#, build_unique_id_dict
import pandapower as pp
import numpy as np
import json
import sys
import os


class PandaPowerBackend(AbstractBackend):
    """Backend implementation that uses `PandaPower <http://www.pandapower.org>`_."""

    valid_extensions = (".json", ".pkl")
    valid_data_structure = {
        "global": ["converged", "f_hz", "sn_mva"],
        "bus": {
            "address_names": ["id"],
            "feature_names": ["in_service", "max_vm_pu", "min_vm_pu", "vn_kv", "res_vm_pu",
                              "res_va_degree", "res_p_mw", "res_q_mvar"]
        },
        "load": {
            "address_names": ["bus", "name"],
            "feature_names": ["const_i_percent", "const_z_percent", "controllable", "in_service",
                              "p_mw", "q_mvar", "scaling", "sn_mva", "res_p_mw", "res_q_mvar"]
        },
        "sgen": {
            "address_names": ["bus", "name"],
            "feature_names": ["controllable", "in_service", "p_mw", "q_mvar", "scaling", "sn_mva",
                              "current_source", "res_p_mw", "res_q_mvar"]
        },
        "gen": {
            "address_names": ["bus", "name"],
            "feature_names": ["controllable", "in_service", "p_mw", "scaling", "sn_mva", "vm_pu",
                              "slack", "max_p_mw", "min_p_mw", "max_q_mvar", "min_q_mvar", "slack_weight",
                              "res_p_mw", "res_q_mvar", "res_va_degree", "res_vm_pu"]
        },
        "shunt": {
            "address_names": ["bus", "name"],
            "feature_names": ["q_mvar", "p_mw", "vn_kv", "step", "max_step", "in_service", "res_p_mw",
                              "res_q_mvar", "res_vm_pu"]
        },
        "ext_grid": {
            "address_names": ["bus", "name"],
            "feature_names": ["in_service", "va_degree", "vm_pu", "max_p_mw", "min_p_mw", "max_q_mvar",
                              "min_q_mvar", "slack_weight", "res_p_mw", "res_q_mvar"]
        },
        "line": {
            "address_names": ["from_bus", "to_bus", "name"],
            "feature_names": ["c_nf_per_km", "df", "g_us_per_km", "in_service", "length_km", "max_i_ka",
                              "max_loading_percent", "parallel", "r_ohm_per_km", "x_ohm_per_km", "res_p_from_mw",
                              "res_q_from_mvar", "res_p_to_mw", "res_q_to_mvar", "res_pl_mw", "res_ql_mvar",
                              "res_i_from_ka", "res_i_to_ka", "res_i_ka", "res_vm_from_pu", "res_va_from_degree",
                              "res_vm_to_pu", "res_va_to_degree", "res_loading_percent"]
        },
        "trafo": {
            "address_names": ["hv_bus", "lv_bus", "name"],
            "feature_names": ["df", "i0_percent", "in_service", "max_loading_percent", "parallel",
                              "pfe_kw", "shift_degree", "sn_mva", "tap_max", "tap_neutral", "tap_min",
                              "tap_phase_shifter", "tap_pos", "tap_side", "tap_step_degree", "tap_step_percent",
                              "vn_hv_kv", "vn_lv_kv", "vk_percent", "vkr_percent", "res_p_hv_mw", "res_q_hv_mvar",
                              "res_p_lv_mw", "res_q_lv_mvar", "res_pl_mw", "res_ql_mvar", "res_i_hv_ka",
                              "res_i_lv_ka", "res_vm_hv_pu", "res_va_hv_degree", "res_vm_lv_pu", "res_va_lv_degree",
                              "res_loading_percent"]
        },
        "poly_cost": {
            "address_names": ["element"],
            "feature_names": ["cp0_eur", "cp1_eur_per_mw", "cp2_eur_per_mw2", "cq0_eur", "cq1_eur_per_mvar",
                              "cq2_eur_per_mvar2"]
        }
    }

    def __init__(self):
        """Initializes a PandaPowerBackend."""
        super().__init__()

    def load_network(self, file_path):
        """Loads a power grid instance, either from a `.pkl` or from a `.json` file."""
        if file_path.endswith('.json'):
            net = pp.from_json(file_path)
        elif file_path.endswith('.pkl'):
            net = pp.from_pickle(file_path)
        else:
            raise NotImplementedError('No support for file {}'.format(file_path))
        return net

    def set_feature_network(self, net, y):
        """Updates a power grid by setting features according to `y`."""
        for k in y.keys():
            for f in y[k].keys():
                try:
                    net[k][f] = y[k][f]
                except ValueError:
                    print('Object {} and key {} are not available with PandaPower'.format(k, f))

    def run_network(self, net, **kwargs):
        """Runs a power flow simulation."""
        try:
            pp.runpp(net, **kwargs)
        except pp.powerflow.LoadflowNotConverged:
            pass

    def get_data_network(self, network, data_structure):
        """"""
        x = {}
        for k in data_structure.keys():
            if k == 'global':
                x[k] = get_global_features(network, data_structure[k])
            else:
                x[k] = get_local_features(network, data_structure[k], k)
        clean_dict(x)
        convert_addresses_to_integers(x)
        return x


def get_global_features(network, feature_names):
    """"""
    r = {}
    for name in feature_names:
        if name == 'converged':
            r[name] = np.array([network.converged], dtype=np.float32)
        elif name == 'f_hz':
            r[name] = np.array([network.f_hz], dtype=np.float32)
        elif name == 'sn_mva':
            r[name] = np.array([network.sn_mva], dtype=np.float32)
        else:
            raise ValueError('{} not an available global feature.'.format(name))
    return r


def get_local_features(network, structure, object_name):
    """"""
    table = get_table(network, object_name)
    r = {}
    address_names = structure.get('address_names', None)
    if address_names is not None:
        r["address"] = {a: table[a].astype(str) for a in address_names}
    feature_names = structure.get('feature_names', None)
    if feature_names is not None:
        r["features"] = {a: np.array(table[a], dtype=np.float32) for a in feature_names}
    return r




        # table_dict = self.get_table_dict(network, k)
        # address_names = data_structure[k]['address_names']
        # if address_names:
        #    x["address"] = {}
        #    for f in address_names:
        #        x[["address"] = table_dict[f]

    # def get_feature_network(self, network, feature_names):
    #     """Returns features from a single power grid instance."""
    #     table_dict = self.get_table_dict(network, feature_names)
    #     x = {k: {f: np.array(xkf, dtype=np.float32) for f, xkf in xk.items()} for k, xk in table_dict.items()}
    #     return clean_dict(x)
    #
    # def get_address_network(self, network, address_names):
    #     """Extracts a nested dict of address ids from a power grid instance."""
    #     table_dict = self.get_table_dict(network, address_names)
    #     id_dict = build_unique_id_dict(table_dict, address_names)
    #     a = {k: {f: np.array(xkf.astype(str).map(id_dict), dtype=np.int32) for f, xkf in xk.items()}
    #          for k, xk in table_dict.items()}
    #     return clean_dict(a)


# def get_table_dict(network, feature_names):
#     """Gets a dict of pandas tables for all the objects in feature_names, from the input network."""
#     return {k: get_table(network, k, f) for k, f in feature_names.items()}


def get_table(net, key):  # , feature_list):
    """Gets a pandas dataframe describing the features of a specific object in a power grid instance.

    Pandapower puts the results of power flow simulations into a separate table. For instance,
    results at buses is stored in net.res_bus. We thus merge the two table by adding a prefix res
    for the considered features.

    """
    if key == 'bus':
        table = net.bus.copy(deep=True)
        table = table.join(net.res_bus.add_prefix('res_'))
    elif key == 'load':
        table = net.load.copy(deep=True)
        table = table.join(net.res_load.add_prefix('res_'))
        table.name = 'load_' + table.index.astype(str)
    elif key == 'sgen':
        table = net.sgen.copy(deep=True)
        table = table.join(net.res_sgen.add_prefix('res_'))
        table.name = 'sgen_' + table.index.astype(str)
    elif key == 'gen':
        table = net.gen.copy(deep=True)
        table = table.join(net.res_gen.add_prefix('res_'))
        table.name = 'gen_' + table.index.astype(str)
    elif key == 'shunt':
        table = net.shunt.copy(deep=True)
        table = table.join(net.res_shunt.add_prefix('res_'))
        table.name = 'shunt_' + table.index.astype(str)
    elif key == 'ext_grid':
        table = net.ext_grid.copy(deep=True)
        table = table.join(net.res_ext_grid.add_prefix('res_'))
        table.name = 'ext_grid_' + table.index.astype(str)
    elif key == 'line':
        table = net.line.copy(deep=True)
        table = table.join(net.res_line.add_prefix('res_'))
        table.name = 'line_' + table.index.astype(str)
    elif key == 'trafo':
        table = net.trafo.copy(deep=True)
        table = table.join(net.res_trafo.add_prefix('res_'))
        table.name = 'trafo_' + table.index.astype(str)
        table.tap_side = table.tap_side.map({'hv': 0., 'lv': 1.})
    elif key == 'poly_cost':
        table = net.poly_cost.copy(deep=True)
        table['element'] = table.et.astype(str) + '_' + table.element.astype(str)
    else:
        raise ValueError('Object {} is not a valid object name. ' +
                         'Please pick from : {}'.format(key, self.valid_feature_names))
    table['id'] = table.index
    table.replace([np.inf], 99999, inplace=True)
    table.replace([-np.inf], -99999, inplace=True)
    table = table.fillna(0.)
    # features_to_keep = list(set(list(table)) & set(feature_list))
    # return table[features_to_keep]
    return table



