import time
import unittest

from django.test import TestCase
import mock

from .factories import ArtistFactory, TrackFactory
from .memory_manager import QuerySet, data_store
from .models import RecordLabel, Artist, Fan, Album, Track


cursor_wrapper = mock.Mock()
cursor_wrapper.side_effect = RuntimeError("No touching the database!")
no_db_tests = mock.patch("django.db.backends.util.CursorWrapper", cursor_wrapper)


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


@no_db_tests
@mock.patch.object(Artist.objects, 'get_query_set', lambda: QuerySet(Artist))
class MemoryManagerSingleModelTests(TestCase):
    def tearDown(self):
        # clear out the data store
        data_store.clear()

    def test_create(self):
        artist = Artist.objects.create(name='Bob')
        self.assertEqual(Artist.objects.get_query_set().query.data_store, [artist])
        self.assertEqual(artist.pk, 1)
        self.assertEqual(artist.id, 1)

    def test_all(self):
        artist = Artist.objects.create(name='Bob')
        artists = Artist.objects.all()
        self.assertSequenceEqual(artists, [artist])
        self.assertTrue(artist is artists[0])

    def test_get(self):
        artist = Artist.objects.create(name='Bob')
        loaded = Artist.objects.get()
        self.assertTrue(artist is loaded)

    def test_get_multiple_objects(self):
        Artist.objects.create(name='Bob')
        Artist.objects.create(name='Bob the second')
        with self.assertRaises(Artist.MultipleObjectsReturned):
            Artist.objects.get()

    def test_get_no_objects(self):
        with self.assertRaises(Artist.DoesNotExist):
            Artist.objects.get()

    def test_filter(self):
        bob = Artist.objects.create(name='Bob')
        Artist.objects.create(name='Bob the second')
        artists = Artist.objects.filter(name='Bob')
        self.assertSequenceEqual(artists, [bob])

    def test_multi_filter(self):
        bob = Artist.objects.create(name='Bob')
        bob2 = Artist.objects.create(name='Bob')
        self.assertEqual(bob.pk, 1)
        self.assertEqual(bob2.pk, 2)
        artists = Artist.objects.filter(name='Bob', pk=2)
        self.assertSequenceEqual(artists, [bob2])

    def test_simple_exclude(self):
        Artist.objects.create(name='Bob')
        bob2 = Artist.objects.create(name='Bob the second')
        artists = Artist.objects.exclude(name='Bob')
        self.assertSequenceEqual(artists, [bob2])

    def test_filter_and_exclude(self):
        bob = Artist.objects.create(name='Bob')
        bob2 = Artist.objects.create(name='Bob')
        self.assertEqual(bob.pk, 1)
        self.assertEqual(bob2.pk, 2)
        artists = Artist.objects.filter(name='Bob').exclude(pk=1)
        self.assertSequenceEqual(artists, [bob2])

    def test_filter_exact(self):
        bob = Artist.objects.create(name='Bob')
        Artist.objects.create(name='Bob the second')
        artists = Artist.objects.filter(name__exact='Bob')
        self.assertSequenceEqual(artists, [bob])

    def test_count(self):
        Artist.objects.create(name='Bob')
        count = Artist.objects.count()
        self.assertEqual(count, 1)

    def test_get_or_create(self):
        artist, created = Artist.objects.get_or_create(name='Bob')
        self.assertTrue(created)
        artist, created = Artist.objects.get_or_create(name='Bob')
        self.assertFalse(created)
        self.assertEqual(Artist.objects.count(), 1)

    def test_delete(self):
        Artist.objects.create(name='Bob')
        Artist.objects.all().delete()
        self.assertEqual(Artist.objects.count(), 0)

    def test_delete_with_filter(self):
        Artist.objects.create(name='Bob')
        Artist.objects.create(name='Dave')
        Artist.objects.filter(name='Dave').delete()
        self.assertEqual(Artist.objects.count(), 1)

    def test_exists(self):
        Artist.objects.create(name='Bob')
        self.assertTrue(Artist.objects.exists())

    def test_update(self):
        Artist.objects.create(name='Bob')
        updated = Artist.objects.update(name='Dave')
        self.assertEqual(Artist.objects.get().name, 'Dave')
        self.assertEqual(updated, 1)

    def test_none(self):
        self.assertSequenceEqual(Artist.objects.none(), [])

    def test_order_by(self):
        bob = Artist.objects.create(name='Bob')
        adam = Artist.objects.create(name='Adam')
        by_pk = Artist.objects.order_by('pk')
        by_name = Artist.objects.order_by('name')
        self.assertSequenceEqual(by_pk, [bob, adam])
        self.assertSequenceEqual(by_name, [adam, bob])

    def test_complex_order_by(self):
        bob = Artist.objects.create(name='Bob')
        bob2 = Artist.objects.create(name='Bob')
        adam = Artist.objects.create(name='Adam')
        ordered = Artist.objects.order_by('name', '-pk')
        self.assertSequenceEqual(ordered, [adam, bob2, bob])


@no_db_tests
@mock.patch.object(Fan.objects, 'get_query_set', lambda: QuerySet(Fan))
@mock.patch.object(Fan.artist, 'get_query_set', lambda instance: QuerySet(Artist))
@mock.patch.object(Artist.objects, 'get_query_set', lambda: QuerySet(Artist))
@mock.patch.object(Artist.fan_set, 'related_manager_cls', lambda self: RelatedQuerySet(Fan, instance=self))
class MemoryManagerFKTests(TestCase):
    def tearDown(self):
        # clear out the data store
        data_store.clear()

    def test_creating_with_fk(self):
        artist = Artist.objects.create(name='Bob')
        Fan.objects.create(name='Annie', artist=artist)
        self.assertEqual(Fan.objects.get().artist, artist)

    def test_creating_with_id(self):
        artist = Artist.objects.create(name='Bob')
        Fan.objects.create(name='Annie', artist_id = artist.pk)
        self.assertEqual(Fan.objects.get().artist, artist)

    def test_reverse_lookup(self):
        artist = Artist.objects.create(name='Bob')
        fan = Fan.objects.create(name='Annie', artist=artist)
        self.assertSequenceEqual(artist.fan_set.all(), [fan])

    def test_reverse_lookup_multiple_objects(self):
        bob = Artist.objects.create(name='Bob')
        annie = Fan.objects.create(name='Annie', artist=bob)
        dave = Artist.objects.create(name='Dave')
        Fan.objects.create(name='Lottie', artist=dave)
        self.assertSequenceEqual(bob.fan_set.all(), [annie])


# TODO:
# Related objects (M2M)
# Save on a model instance
# Complex Lookups (contains, in, iexact, icontains, related)
