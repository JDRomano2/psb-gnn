from dgl import DGLGraph, NID, subgraph, node_subgraph
from dgl.transform import add_self_loop
from torch.utils.data import DataLoader, Dataset
from dgl.dataloading.negative_sampler import Uniform
import torch

class GraphDataset(Dataset):
    """A graph dataset adapter for torch's DataLoader.
    """

    def __init__(self, graph_list, tensor):
        self.graph_list = graph_list
        self.tensor = tensor

    def __len__(self):
        return len(self.graph_list)

    def __getitem__(self, index):
        return (self.graph_list[index], self.tensor[index])

class PosNegEdgesGenerator(object):
    """Generates positive and negative samples from a graph.

    Parameters
    ----------
    g : dgl.DGLHeteroGraph
        Heterogeneous graph to sample.
    split_edge : dict
        
    neg_samples : int
        Number of negative samples to draw per positive sample.
    subsample_ratio : float

    shuffle : bool
        Whether to shuffle list of generated graphs.
    """
    def __init__(self, g, split_edge, neg_samples=1, subsample_ratio=0.1, shuffle=True):
        self.neg_sampler = Uniform(neg_samples)
        self.subsample_ratio = subsample_ratio
        self.split_edge = split_edge
        self.g = g
        self.shuffle = shuffle

    def __call__(self, split_type):
        if split_type == 'train':
            subsample_ratio = self.subsample_ratio
        else:
            subsample_ratio = 1

        pos_edges = self.split_edge[split_type]['edge']
        if split_type == 'train':
            # Add self-loops so the identity node features don't 'wash out',
            # but do it in training only so we don't sample the start node
            g = add_self_loop(self.g)
            eids = g.edge_ids()
            neg_edges = torch.stack(self.neg_sampler(g, eids), dim=1)
        else:
            neg_edges = self.split_edge[split_type]['edge_neg']
        pos_edges = self.subsample(pos_edges, subsample_ratio).long()
        neg_edges = self.subsample(neg_edges, subsample_ratio).long()

        edges = torch.cat([pos_edges, neg_edges])
        labels = torch.cat([torch.ones(pos_edges.size(0), 1), torch.zeros(neg_edges.size(0), 1)])
        if self.shuffle:
            perm = torch.randperm(edges.size(0))
            edges = edges[perm]
            labels = labels[perm]
        return edges, labels

    def subsample(self, edges, subsample_ratio):
        """Subsample the edges generated by calling the edge generator.

        Parameters
        ----------
        edges : torch.Tensor
            Edges from which to pull the subsample.
        subsample_ratio : float
            Ratio of subsample w.r.t. the size of `edges`.

        Returns
        -------
        edges : torch.Tensor
            Subsampled edges.
        """
        num_edges = edges.size(0)
        perm = torch.randperm(num_edges)
        perm = perm[:int(subsample_ratio * num_edges)]
        edges = edges[perm]
        return edges

class EdgeDataSet(Dataset):
    def __init__(self, edges, labels, transform):
        self.edges = edges
        self.labels = labels
        self.transform = transform

    def __len__(self):
        return len(self.edges)

    def __getitem__(self, index):
        subgraph = self.transform(self.edges[index])
        return (subgraph, self.labels[index])

class QSARSampler(object):
    """Sampler for QSAR data; modeled using code for the SEAL paper.

    Briefly, sampling involves taking all k-hop neighbors around 
    """
    def __init__(self, graph, hop=1, num_workers=32, print_fn=print):
        self.graph = graph
        self.hop = hop
        self.print_fn = print_fn
        self.num_workers = num_workers

    def sample_subgraph(self, target_nodes):
        sample_nodes = [target_nodes]
        frontiers = target_nodes

        for i in range(self.hop):
            frontiers = self.graph.out_edges(frontiers)[1]
            frontiers = torch.unique(frontiers)
            sample_nodes.append(frontiers)

        sample_nodes = torch.cat(sample_nodes)
        sample_nodes = torch.unique(sample_nodes)
        subgraph = dgl.node_subgraph(self.graph, sample_nodes)

        # Make sure that we have unique node ids
        u_id = int(torch.nonzero(subgraph.ndata[NID] == int(target_nodes[0]), as_tuple=False))
        v_id = int(torch.nonzero(subgraph.ndata[NID] == int(target_nodes[0]), as_tuple=False))

        # Remove links between target nodes in the positive subgraphs
        if subgraph.has_edges_between(u_id, v_id):
            link_id = subgraph.edge_ids(u_id, v_id, return_uv=True)[2]
            subgraph.remove_edges(link_id)
        # Now remove those in the opposite direction
        if subgraph.has_edges_between(v_id, u_id):
            link_id = subgraph.edge_ids(u_id, v_id, return_uv=True)[2]
            subgraph.remove_edges(link_id)

        #z = drnl_node_labeling(subgraph, u_id, v_id)

class QSARData(object):
    pass