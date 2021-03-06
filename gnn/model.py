#!/usr/bin/env python3

import dgl.function as fn
from numpy import e
import torch
import torch.nn as nn
import torch.nn.functional as F

import ipdb

# if torch.cuda.is_available():
#     DEVICE = 'cuda:0'
# else:
#     DEVICE = 'cpu'
DEVICE = 'cpu'

class HeteroRGCNLayer(nn.Module):
    """Graph convolutional layer for relational data that supports
    multiple edge types.

    Parameters
    ----------
    in_size_dict : int or dict of int
        A dictionary mapping edge types to their input size. For any given edge
        type, the input size is equal to the dimensionality of the source
        node's feature matrix.
    out_size : int
        Number of output features for the graph convolutional layer.
    etypes : list of str
        List of strings representing the names of all edge types in the graph.
    """
    def __init__(self, in_size, out_size, etypes):
        super(HeteroRGCNLayer, self).__init__()

        if isinstance(in_size, dict):
            self.weight = nn.ModuleDict({
                name: nn.Linear(in_size[name], out_size).to(DEVICE) for name in etypes
            })
        else:
            self.weight = nn.ModuleDict({
                name: nn.Linear(in_size, out_size).to(DEVICE) for name in etypes
            })

    def forward(self, G, feat_dict):
        funcs = {}
        for srctype, etype, dsttype in G.canonical_etypes:
            Wh = self.weight[etype](feat_dict[srctype]).to(DEVICE)

            G.nodes[srctype].data['Wh_%s' % etype] = Wh

            funcs[etype] = (fn.copy_u('Wh_%s' % etype, 'm'), fn.mean('m', 'h'))

        G.multi_update_all(funcs, 'sum')

        return { ntype : G.nodes[ntype].data['h'] for ntype in G.ntypes }

class HeteroDotProductPredictor(nn.Module):
    def forward(self, G, h, etype):
        with G.local_scope():
            G.ndata['h'] = h
            G.apply_edges(fn.u_dot_v('h', 'h', 'score'), etype=etype)
            return G.edges[etype].data['score']
