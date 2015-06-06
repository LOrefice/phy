# -*- coding: utf-8 -*-

"""Tests of session structure."""

#------------------------------------------------------------------------------
# Imports
#------------------------------------------------------------------------------

import os.path as op

import numpy as np
from numpy.testing import assert_allclose as ac
from numpy.testing import assert_array_equal as ae
from pytest import raises, mark, fixture

from ..session import Session
from ...utils import _spikes_in_clusters
from ...utils.testing import (show_test_start, show_test_run,
                              show_test_stop,
                              )
from ...gui.qt import qt_app, _close_qt_after, wrap_qt
from ...utils.tempdir import TemporaryDirectory
from ...utils.logging import set_level
from ...io.mock import MockModel
from ...io.kwik.mock import create_mock_kwik


#------------------------------------------------------------------------------
# Kwik tests
#------------------------------------------------------------------------------

_N_FRAMES = 2


def setup():
    set_level('info')


def _start_manual_clustering(kwik_path=None,
                             model=None,
                             tempdir=None,
                             chunk_size=None,
                             ):
    session = Session(phy_user_dir=tempdir)
    if chunk_size is not None:
        session.settings['features_masks_chunk_size'] = chunk_size
    session.open(kwik_path=kwik_path, model=model)
    return session


def test_session_store_features():
    """Check that the cluster store works for features and masks."""

    with TemporaryDirectory() as tempdir:
        model = MockModel(n_spikes=50, n_clusters=3)
        s0 = np.nonzero(model.spike_clusters == 0)[0]
        s1 = np.nonzero(model.spike_clusters == 1)[0]

        session = _start_manual_clustering(model=model,
                                           tempdir=tempdir,
                                           chunk_size=4,
                                           )

        f = session.cluster_store.features(0)
        m = session.cluster_store.masks(1)
        w = session.cluster_store.waveforms(1)

        assert f.shape == (len(s0), 28, 2)
        assert m.shape == (len(s1), 28,)
        assert w.shape == (len(s1), model.n_samples_waveforms, 28,)

        ac(f, model.features[s0].reshape((f.shape[0], -1, 2)), 1e-3)
        ac(m, model.masks[s1], 1e-3)


n_clusters = 5
n_spikes = 50
n_channels = 28
n_fets = 2
n_samples_traces = 3000


@fixture
def session(request):
    tmpdir = TemporaryDirectory()

    # Create the test HDF5 file in the temporary directory.
    kwik_path = create_mock_kwik(tmpdir.name,
                                 n_clusters=n_clusters,
                                 n_spikes=n_spikes,
                                 n_channels=n_channels,
                                 n_features_per_channel=n_fets,
                                 n_samples_traces=n_samples_traces)

    session = _start_manual_clustering(kwik_path=kwik_path,
                                       tempdir=tmpdir.name)
    session.tempdir = tmpdir.name

    def end():
        session.close()
        tmpdir.cleanup()
    request.addfinalizer(end)

    return session


@wrap_qt
def test_session_clustering(session):

    cs = session.cluster_store
    spike_clusters = session.model.spike_clusters.copy()

    f = session.model.features
    m = session.model.masks

    def _check_arrays(cluster, clusters_for_sc=None, spikes=None):
        """Check the features and masks in the cluster store
        of a given custer."""
        if spikes is None:
            if clusters_for_sc is None:
                clusters_for_sc = [cluster]
            spikes = _spikes_in_clusters(spike_clusters, clusters_for_sc)
        shape = (len(spikes),
                 len(session.model.channel_order),
                 session.model.n_features_per_channel)
        ac(cs.features(cluster), f[spikes, :].reshape(shape))
        ac(cs.masks(cluster), m[spikes])

    _check_arrays(0)
    _check_arrays(2)

    gui = session.show_gui()
    yield

    # Merge two clusters.
    clusters = [0, 2]
    gui.merge(clusters)  # Create cluster 5.
    _check_arrays(5, clusters)
    yield

    # Split some spikes.
    spikes = [2, 3, 5, 7, 11, 13]
    # clusters = np.unique(spike_clusters[spikes])
    gui.split(spikes)  # Create cluster 6 and more.
    _check_arrays(6, spikes=spikes)
    yield

    # Undo.
    gui.undo()
    _check_arrays(5, clusters)
    yield

    # Undo.
    gui.undo()
    _check_arrays(0)
    _check_arrays(2)
    yield

    # Redo.
    gui.redo()
    _check_arrays(5, clusters)
    yield

    # Split some spikes.
    spikes = [5, 7, 11, 13, 17, 19]
    # clusters = np.unique(spike_clusters[spikes])
    gui.split(spikes)  # Create cluster 6 and more.
    _check_arrays(6, spikes=spikes)
    yield

    # Test merge-undo-different-merge combo.
    spc = gui.clustering.spikes_per_cluster.copy()
    clusters = gui.cluster_ids[:3]
    up = gui.merge(clusters)
    _check_arrays(up.added[0], spikes=up.spike_ids)
    # Undo.
    gui.undo()
    for cluster in clusters:
        _check_arrays(cluster, spikes=spc[cluster])
    # Another merge.
    clusters = gui.cluster_ids[1:5]
    up = gui.merge(clusters)
    _check_arrays(up.added[0], spikes=up.spike_ids)
    yield

    # Move a cluster to a group.
    cluster = gui.cluster_ids[0]
    gui.move([cluster], 2)
    assert len(gui.store.mean_probe_position(cluster)) == 2
    yield

    # Save.
    spike_clusters_new = gui.model.spike_clusters.copy()
    # Check that the spike clusters have changed.
    assert not np.all(spike_clusters_new == spike_clusters)
    ac(session.model.spike_clusters, gui.clustering.spike_clusters)
    session.save()
    yield

    # Re-open the file and check that the spike clusters and
    # cluster groups have correctly been saved.
    session = _start_manual_clustering(kwik_path=session.model.path,
                                       tempdir=session.tempdir)
    ac(session.model.spike_clusters, gui.clustering.spike_clusters)
    ac(session.model.spike_clusters, spike_clusters_new)
    #  Check the cluster groups.
    clusters = gui.clustering.cluster_ids
    groups = session.model.cluster_groups
    assert groups[cluster] == 2
    yield

    gui.close()


@wrap_qt
def test_session_multiple_clusterings(session):

    gui = session.show_gui()
    yield

    assert session.model.n_spikes == n_spikes
    assert session.model.n_clusters == n_clusters
    assert len(session.model.cluster_ids) == n_clusters
    assert gui.clustering.n_clusters == n_clusters
    assert session.model.cluster_metadata.group(1) == 1

    # Change clustering.
    with raises(ValueError):
        session.change_clustering('automat')
    session.change_clustering('automatic')
    yield

    assert session.model.n_spikes == n_spikes
    assert session.model.n_clusters == n_clusters * 2
    assert len(session.model.cluster_ids) == n_clusters * 2
    assert gui.clustering.n_clusters == n_clusters * 2
    assert session.model.cluster_metadata.group(2) == 2

    # Merge the clusters and save, for the current clustering.
    gui.clustering.merge(gui.clustering.cluster_ids)
    session.save()
    yield

    # Re-open the session.
    session = _start_manual_clustering(kwik_path=session.model.path,
                                       tempdir=session.tempdir)
    yield

    # The default clustering is the main one: nothing should have
    # changed here.
    assert session.model.n_clusters == n_clusters

    session.change_clustering('automatic')
    assert session.model.n_spikes == n_spikes
    assert session.model.n_clusters == 1
    assert session.model.cluster_ids == n_clusters * 2
    yield

    gui.close()


def test_session_kwik():
    n_clusters = 5
    n_spikes = 50
    n_channels = 28
    n_fets = 2
    n_samples_traces = 3000

    with TemporaryDirectory() as tempdir:

        # Create the test HDF5 file in the temporary directory.
        kwik_path = create_mock_kwik(tempdir,
                                     n_clusters=n_clusters,
                                     n_spikes=n_spikes,
                                     n_channels=n_channels,
                                     n_features_per_channel=n_fets,
                                     n_samples_traces=n_samples_traces)

        session = _start_manual_clustering(kwik_path=kwik_path,
                                           tempdir=tempdir)

        # Check backup.
        assert op.exists(op.join(tempdir, kwik_path + '.bak'))

        cs = session.cluster_store

        nc = n_channels - 2

        # Check the stored items.
        for cluster in range(n_clusters):
            n_spikes = len(gui.clustering.spikes_per_cluster[cluster])
            n_unmasked_channels = cs.n_unmasked_channels(cluster)

            assert cs.features(cluster).shape == (n_spikes, nc, n_fets)
            assert cs.masks(cluster).shape == (n_spikes, nc)
            assert cs.mean_masks(cluster).shape == (nc,)
            assert n_unmasked_channels <= nc
            assert cs.mean_probe_position(cluster).shape == (2,)
            assert cs.main_channels(cluster).shape == (n_unmasked_channels,)

        session.close()


def test_session_wizard():

    n_clusters = 5
    n_spikes = 100
    n_channels = 28
    n_fets = 2
    n_samples_traces = 3000

    with TemporaryDirectory() as tempdir:

        # Create the test HDF5 file in the temporary directory.
        kwik_path = create_mock_kwik(tempdir,
                                     n_clusters=n_clusters,
                                     n_spikes=n_spikes,
                                     n_channels=n_channels,
                                     n_features_per_channel=n_fets,
                                     n_samples_traces=n_samples_traces)

        session = _start_manual_clustering(kwik_path=kwik_path,
                                           tempdir=tempdir)

        clusters = np.arange(n_clusters)
        best_clusters = session.wizard.best_clusters()

        # assert session.wizard.best_clusters(1)[0] == best_clusters[0]
        ae(np.unique(best_clusters), clusters)
        assert len(session.wizard.most_similar_clusters()) == n_clusters - 1

        assert len(session.wizard.most_similar_clusters(0, n_max=3)) == 3

        session.merge([0, 1, 2])
        assert np.all(np.in1d(session.wizard.best_clusters(), np.arange(3, 6)))
        assert list(session.wizard.most_similar_clusters(5)) in ([3, 4],
                                                                 [4, 3])

        # Move a cluster to noise.
        session.move([5], 0)
        best = session.wizard.best_clusters(1)[0]
        if best is not None:
            assert best in (3, 4)
            # The most similar cluster is 3 if best=4 and conversely.
            assert session.wizard.most_similar_clusters(best)[0] == 7 - best


def test_session_statistics():
    """Test registration of new statistic."""
    n_clusters = 5
    n_spikes = 100
    n_channels = 28
    n_fets = 2
    n_samples_traces = 3000

    with TemporaryDirectory() as tempdir:

        # Create the test HDF5 file in the temporary directory.
        kwik_path = create_mock_kwik(tempdir,
                                     n_clusters=n_clusters,
                                     n_spikes=n_spikes,
                                     n_channels=n_channels,
                                     n_features_per_channel=n_fets,
                                     n_samples_traces=n_samples_traces)

        session = _start_manual_clustering(kwik_path=kwik_path,
                                           tempdir=tempdir)

        @session.register_statistic
        def n_spikes_2(cluster):
            return gui.clustering.cluster_counts.get(cluster, 0) ** 2

        store = session.cluster_store
        stats = store.items['statistics']

        def _check():
            for clu in session.cluster_ids:
                assert (store.n_spikes_2(clu) ==
                        store.features(clu).shape[0] ** 2)

        assert 'n_spikes_2' in stats.fields
        _check()

        # Merge the clusters and check that the statistics has been
        # recomputed for the new cluster.
        clusters = session.cluster_ids
        session.merge(clusters)
        _check()
        assert session.cluster_ids == [max(clusters) + 1]

        session.undo()
        _check()

        session.merge(session.cluster_ids[::2])
        _check()


@mark.long
def test_session_history():

    n_clusters = 15
    n_spikes = 300
    n_channels = 28
    n_fets = 2
    n_samples_traces = 10000

    with TemporaryDirectory() as tempdir:

        # Create the test HDF5 file in the temporary directory.
        kwik_path = create_mock_kwik(tempdir,
                                     n_clusters=n_clusters,
                                     n_spikes=n_spikes,
                                     n_channels=n_channels,
                                     n_features_per_channel=n_fets,
                                     n_samples_traces=n_samples_traces)

        session = _start_manual_clustering(kwik_path=kwik_path,
                                           tempdir=tempdir)

        session.wizard.start()

        spikes = _spikes_in_clusters(session.model.spike_clusters,
                                     session.wizard.selection)
        session.split(spikes[::3])
        session.undo()
        session.wizard.next()
        session.redo()
        session.undo()

        for _ in range(10):
            session.merge(session.wizard.selection)
            session.wizard.next()
            session.undo()
            session.wizard.next()
            session.redo()
            session.wizard.next()

            spikes = _spikes_in_clusters(session.model.spike_clusters,
                                         session.wizard.selection)
            if len(spikes):
                session.split(spikes[::10])
                session.wizard.next()
                session.undo()
            session.merge(session.wizard.selection)
            session.wizard.next()
            session.wizard.next()

            session.wizard.next_best()
            ae(session.model.spike_clusters, gui.clustering.spike_clusters)


@mark.long
def test_session_gui():
    n_clusters = 15
    n_spikes = 500
    n_channels = 30
    n_fets = 3
    n_samples_traces = 50000

    with TemporaryDirectory() as tempdir:

        # Create the test HDF5 file in the temporary directory.
        kwik_path = create_mock_kwik(tempdir,
                                     n_clusters=n_clusters,
                                     n_spikes=n_spikes,
                                     n_channels=n_channels,
                                     n_features_per_channel=n_fets,
                                     n_samples_traces=n_samples_traces)

        session = _start_manual_clustering(kwik_path=kwik_path,
                                           tempdir=tempdir)

        with qt_app():
            config = session.settings['gui_config']
            for name, kwargs in config:
                if name in ('waveforms', 'features', 'traces'):
                    kwargs['scale_factor'] = 1
            gui = session.gui_creator.add(config=config, show=False)
            _close_qt_after(gui, 0.25)
            gui.show()
