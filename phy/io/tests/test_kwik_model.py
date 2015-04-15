# -*- coding: utf-8 -*-

"""Tests of Kwik file opening routines."""

#------------------------------------------------------------------------------
# Imports
#------------------------------------------------------------------------------

import numpy as np
from numpy.testing import assert_array_equal as ae
from pytest import raises

from ...electrode.mea import MEA, staggered_positions
from ...utils.tempdir import TemporaryDirectory
from ..kwik_model import (KwikModel,
                          _list_channel_groups,
                          _list_channels,
                          _list_recordings,
                          _list_clusterings,
                          _concatenate_spikes,
                          )
from ..mock.kwik import create_mock_kwik


#------------------------------------------------------------------------------
# Tests
#------------------------------------------------------------------------------

_N_CLUSTERS = 10
_N_SPIKES = 100
_N_CHANNELS = 28
_N_FETS = 2
_N_SAMPLES_TRACES = 10000


def test_kwik_utility():

    channels = list(range(_N_CHANNELS))

    with TemporaryDirectory() as tempdir:
        # Create the test HDF5 file in the temporary directory.
        filename = create_mock_kwik(tempdir,
                                    n_clusters=_N_CLUSTERS,
                                    n_spikes=_N_SPIKES,
                                    n_channels=_N_CHANNELS,
                                    n_features_per_channel=_N_FETS,
                                    n_samples_traces=_N_SAMPLES_TRACES)
        model = KwikModel(filename)

        model._kwik.open()
        assert _list_channel_groups(model._kwik.h5py_file) == [1]
        assert _list_recordings(model._kwik.h5py_file) == [0, 1]
        assert _list_clusterings(model._kwik.h5py_file, 1) == ['main',
                                                               'automatic',
                                                               ]
        assert _list_channels(model._kwik.h5py_file, 1) == channels


def test_concatenate_spikes():
    spikes = [2, 3, 5, 0, 11, 1]
    recs = [0, 0, 0, 1, 1, 2]
    offsets = [0, 7, 100]
    concat = _concatenate_spikes(spikes, recs, offsets)
    ae(concat, [2, 3, 5, 7, 18, 101])


def test_kwik_open_full():

    with TemporaryDirectory() as tempdir:
        # Create the test HDF5 file in the temporary directory.
        filename = create_mock_kwik(tempdir,
                                    n_clusters=_N_CLUSTERS,
                                    n_spikes=_N_SPIKES,
                                    n_channels=_N_CHANNELS,
                                    n_features_per_channel=_N_FETS,
                                    n_samples_traces=_N_SAMPLES_TRACES)

        with raises(ValueError):
            KwikModel()

        # NOTE: n_channels - 2 because we use a special channel order.
        nc = _N_CHANNELS - 2

        # Test implicit open() method.
        kwik = KwikModel(filename)

        kwik.metadata
        ae(kwik.channels, np.arange(_N_CHANNELS))
        assert kwik.n_channels == _N_CHANNELS
        assert kwik.n_spikes == _N_SPIKES
        ae(kwik.channel_order, np.arange(1, _N_CHANNELS - 1)[::-1])

        assert kwik.spike_samples.shape == (_N_SPIKES,)
        assert kwik.spike_samples.dtype == np.uint64

        # Make sure the spike samples are increasing, even with multiple
        # recordings.
        # WARNING: need to cast to int64, otherwise negative values will
        # overflow and be positive, making the test pass while the
        # spike samples are *not* increasing!
        assert np.all(np.diff(kwik.spike_samples.astype(np.int64)) >= 0)

        assert kwik.spike_times.shape == (_N_SPIKES,)
        assert kwik.spike_times.dtype == np.float64

        assert kwik.spike_recordings.shape == (_N_SPIKES,)
        assert kwik.spike_recordings.dtype == np.uint16

        assert kwik.spike_clusters.shape == (_N_SPIKES,)
        assert kwik.spike_clusters.min() in (0, 1, 2)
        assert kwik.spike_clusters.max() in(_N_CLUSTERS - 2, _N_CLUSTERS - 1)

        assert kwik.features.shape == (_N_SPIKES, nc * _N_FETS)
        kwik.features[0, ...]

        assert kwik.masks.shape == (_N_SPIKES, nc)

        assert kwik.traces.shape == (_N_SAMPLES_TRACES, _N_CHANNELS)

        assert kwik.waveforms[0].shape == (1, 40, nc)
        assert kwik.waveforms[-1].shape == (1, 40, nc)
        assert kwik.waveforms[-10].shape == (1, 40, nc)
        assert kwik.waveforms[10].shape == (1, 40, nc)
        assert kwik.waveforms[[10, 20]].shape == (2, 40, nc)
        with raises(IndexError):
            kwik.waveforms[_N_SPIKES + 10]

        with raises(ValueError):
            kwik.clustering = 'foo'
        with raises(ValueError):
            kwik.channel_group = 42
        assert kwik.n_recordings == 2

        # Test cluster groups.
        for cluster in range(_N_CLUSTERS):
            assert kwik.cluster_metadata.group(cluster) == 3
        for cluster, group in kwik.cluster_groups.items():
            assert group == 3

        # Test probe.
        assert isinstance(kwik.probe, MEA)
        assert kwik.probe.positions.shape == (nc, 2)
        ae(kwik.probe.positions, staggered_positions(_N_CHANNELS)[1:-1][::-1])

        kwik.close()


def test_kwik_open_no_kwx():

    with TemporaryDirectory() as tempdir:
        # Create the test HDF5 file in the temporary directory.
        filename = create_mock_kwik(tempdir,
                                    n_clusters=_N_CLUSTERS,
                                    n_spikes=_N_SPIKES,
                                    n_channels=_N_CHANNELS,
                                    n_features_per_channel=_N_FETS,
                                    n_samples_traces=_N_SAMPLES_TRACES,
                                    with_kwx=False)

        # Test implicit open() method.
        kwik = KwikModel(filename)
        kwik.close()


def test_kwik_open_no_kwd():

    with TemporaryDirectory() as tempdir:
        # Create the test HDF5 file in the temporary directory.
        filename = create_mock_kwik(tempdir,
                                    n_clusters=_N_CLUSTERS,
                                    n_spikes=_N_SPIKES,
                                    n_channels=_N_CHANNELS,
                                    n_features_per_channel=_N_FETS,
                                    n_samples_traces=_N_SAMPLES_TRACES,
                                    with_kwd=False)

        # Test implicit open() method.
        kwik = KwikModel(filename)
        kwik.close()


def test_kwik_save():

    with TemporaryDirectory() as tempdir:
        # Create the test HDF5 file in the temporary directory.
        filename = create_mock_kwik(tempdir,
                                    n_clusters=_N_CLUSTERS,
                                    n_spikes=_N_SPIKES,
                                    n_channels=_N_CHANNELS,
                                    n_features_per_channel=_N_FETS,
                                    n_samples_traces=_N_SAMPLES_TRACES)

        kwik = KwikModel(filename)

        cluster_groups = {cluster: kwik.cluster_metadata.group(cluster)
                          for cluster in range(_N_CLUSTERS)}
        sc_0 = kwik.spike_clusters.copy()
        sc_1 = sc_0.copy()
        new_cluster = _N_CLUSTERS + 10
        sc_1[_N_SPIKES // 2:] = new_cluster
        cluster_groups[new_cluster] = 7
        ae(kwik.spike_clusters, sc_0)

        assert kwik.cluster_metadata.group(new_cluster) == 3
        kwik.save(sc_1, cluster_groups)
        ae(kwik.spike_clusters, sc_1)
        assert kwik.cluster_metadata.group(new_cluster) == 7

        kwik.close()

        kwik = KwikModel(filename)
        ae(kwik.spike_clusters, sc_1)
        assert kwik.cluster_metadata.group(new_cluster) == 7


def test_kwik_clusterings():

    with TemporaryDirectory() as tempdir:
        # Create the test HDF5 file in the temporary directory.
        filename = create_mock_kwik(tempdir,
                                    n_clusters=_N_CLUSTERS,
                                    n_spikes=_N_SPIKES,
                                    n_channels=_N_CHANNELS,
                                    n_features_per_channel=_N_FETS,
                                    n_samples_traces=_N_SAMPLES_TRACES)

        kwik = KwikModel(filename)
        assert kwik.clusterings == ['main', 'automatic']

        # The default clustering is 'main'.
        assert kwik.n_spikes == _N_SPIKES
        assert kwik.n_clusters == _N_CLUSTERS
        assert kwik.cluster_groups[_N_CLUSTERS - 1] == 3
        ae(kwik.cluster_ids, np.arange(_N_CLUSTERS))

        # Change clustering.
        kwik.clustering = 'automatic'
        n_clu = kwik.n_clusters
        assert kwik.n_spikes == _N_SPIKES
        # Some clusters may be empty with a small number of spikes like here
        assert _N_CLUSTERS * 2 - 4 <= n_clu <= _N_CLUSTERS * 2
        assert kwik.cluster_groups[n_clu - 1] == 3
        assert len(kwik.cluster_ids) == n_clu

        # Test renaming.
        with raises(ValueError):
            kwik.rename_clustering('a', 'b')
        with raises(ValueError):
            kwik.rename_clustering('automatic', 'b')
        with raises(ValueError):
            kwik.rename_clustering('main', 'automatic')

        kwik.clustering = 'main'
        kwik.rename_clustering('automatic', 'original')
        assert kwik.clusterings == ['main', 'original']
        with raises(ValueError):
            kwik.clustering = 'automatic'
        kwik.clustering = 'original'
        assert kwik.cluster_groups[n_clu - 1] == 3
        assert len(kwik.cluster_ids) == n_clu

        # Test copy.
        with raises(ValueError):
            kwik.copy_clustering('a', 'b')
        with raises(ValueError):
            kwik.copy_clustering('original', 'b')
        with raises(ValueError):
            kwik.copy_clustering('main', 'original')

        kwik.clustering = 'main'
        kwik.copy_clustering('original', 'automatic')
        assert kwik.clusterings == ['main', 'automatic', 'original']

        kwik.clustering = 'automatic'
        cg = kwik.cluster_groups
        ci = kwik.cluster_ids

        kwik.clustering = 'original'
        assert kwik.cluster_groups == cg
        ae(kwik.cluster_ids, ci)
