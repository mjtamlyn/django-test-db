import time
import unittest

from django.test import TestCase
import mock

from .factories import ArtistFactory, TrackFactory
from .models import RecordLabel, Artist, Album, Track


correct_details = {
    'number': 1,
    'name': 'Tears of a Clown',
    'album': 'All time circus classics',
    'artist': 'Freddy the Clown',
    'collaborators': ['Buttercup'],
    'label': 'Circus Music',
}


class TrackUnicodeTests(TestCase):
    def test_naive(self):
        with self.assertNumQueries(8):
            label = RecordLabel.objects.create(name='Circus Music')
            artist = Artist.objects.create(name='Freddy the Clown')
            album = Album.objects.create(name='All time circus classics', label=label, artist=artist)
            track = Track.objects.create(number=1, name='Tears of a Clown', album=album)
            other_artist = Artist.objects.create(name='Buttercup')
            track.collaborators.add(other_artist)
            self.assertEqual(track.track_details(), correct_details)

    def test_factories(self):
        with self.assertNumQueries(8):
            track = TrackFactory.create(number=1)
            other_artist = Artist.objects.create(name='Buttercup')
            track.collaborators.add(other_artist)
            self.assertEqual(track.track_details(), correct_details)

    def test_factories_build_m2m_problem(self):
        with self.assertNumQueries(4):
            track = TrackFactory.build()
            track.pk = 1
            other_artist = ArtistFactory.create(name='Buttercup')
            track.collaborators.add(other_artist)
            self.assertEqual(track.track_details(), correct_details)

    def test_factories_build_prefetch(self):
        # this one will get even better/easier with #17001
        with self.assertNumQueries(0):
            track = TrackFactory.build()
            track.pk = 1
            other_artist = ArtistFactory.build(name='Buttercup')
            collaborators = track.collaborators.all()
            collaborators._result_cache = [other_artist]
            track._prefetched_objects_cache = {'collaborators': collaborators}
            self.assertEqual(track.track_details(), correct_details)

    def test_factories_build_mock(self):
        with self.assertNumQueries(0):
            other_artist = ArtistFactory.build(name='Buttercup')
            collaborators_mock = mock.MagicMock()
            collaborators_mock.all.return_value = [other_artist]
            with mock.patch('music.factories.Track.collaborators', collaborators_mock):
                track = TrackFactory.build()
                track.pk = 1
                with mock.patch.object(track, 'collaborators', collaborators_mock):
                    self.assertEqual(track.track_details(), correct_details)

    @unittest.skip('Skip!')
    def test_performance_difference(self):
        for test in [self.test_naive, self.test_factories, self.test_factories_build_prefetch, self.test_factories_build_mock]:
            start = time.time()
            for i in range(1000):
                test()
            elapsed = (time.time() - start)
            print test.__name__, elapsed

