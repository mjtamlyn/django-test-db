import time
import unittest

from django.test import TestCase
import mock

from memory_manager import QuerySet, data_store, get_related_queryset, add_items, clear_items, remove_items
from .factories import ArtistFactory, TrackFactory
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
            other_artist = ArtistFactory(name='Buttercup')
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
                self.assertEqual(track.track_details(), correct_details)

    @no_db_tests
    @mock.patch.object(RecordLabel.objects, 'get_queryset', lambda: QuerySet(RecordLabel))
    @mock.patch.object(Artist.objects, 'get_queryset', lambda: QuerySet(Artist))
    @mock.patch.object(Album.objects, 'get_queryset', lambda: QuerySet(Album))
    @mock.patch.object(Track.objects, 'get_queryset', lambda: QuerySet(Track))
    @mock.patch.object(Artist.collaborations.related_manager_cls, 'get_queryset', lambda instance: QuerySet(Artist))
    @mock.patch.object(Track.collaborators.related_manager_cls, 'get_queryset', get_related_queryset)
    @mock.patch.object(Track.collaborators.related_manager_cls, '_add_items', add_items)
    def test_using_memory_manager(self):
        # Exactly the same code as the naive version
        with self.assertNumQueries(0):
            label = RecordLabel.objects.create(name='Circus Music')
            artist = Artist.objects.create(name='Freddy the Clown')
            album = Album.objects.create(name='All time circus classics', label=label, artist=artist)
            track = Track.objects.create(number=1, name='Tears of a Clown', album=album)
            other_artist = Artist.objects.create(name='Buttercup')
            track.collaborators.add(other_artist)
            self.assertEqual(track.track_details(), correct_details)
        data_store.clear()

    @unittest.skip('Skip!')
    def test_performance_difference(self):
        for test in [self.test_naive, self.test_factories, self.test_factories_build_prefetch, self.test_factories_build_mock, self.test_using_memory_manager]:
            start = time.time()
            for i in range(1000):
                test()
            elapsed = (time.time() - start)
            print test.__name__, elapsed


@no_db_tests
@mock.patch.object(Artist.objects, 'get_queryset', lambda: QuerySet(Artist))
class MemoryManagerSingleModelTests(TestCase):
    def tearDown(self):
        # clear out the data store
        data_store.clear()

    def test_create(self):
        artist = Artist.objects.create(name='Bob')
        self.assertEqual(Artist.objects.get_queryset().query.data_store, [artist])
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

    def test_slice(self):
        bob1 = Artist.objects.create(name='Bob1')
        bob2 = Artist.objects.create(name='Bob2')
        bob3 = Artist.objects.create(name='Bob3')
        self.assertSequenceEqual(Artist.objects.all()[:2], [bob1, bob2])
        self.assertSequenceEqual(Artist.objects.all()[1:2], [bob2])
        self.assertSequenceEqual(Artist.objects.all()[1:], [bob2, bob3])
        self.assertSequenceEqual(Artist.objects.all()[::2], [bob1, bob3])

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

    def test_contains_lookup(self):
        bob = Artist.objects.create(name='Bob')
        bobby = Artist.objects.create(name='Bobby')
        Artist.objects.create(name='Adam')
        self.assertSequenceEqual(Artist.objects.filter(name__contains='ob'), [bob, bobby])

    def test_in_lookup(self):
        bob = Artist.objects.create(name='Bob')
        bobby = Artist.objects.create(name='Bobby')
        Artist.objects.create(name='Adam')
        self.assertSequenceEqual(Artist.objects.filter(name__in=['Bob', 'Bobby', 'Fred']), [bob, bobby])

    def test_iexact_lookup(self):
        bob = Artist.objects.create(name='Bob')
        Artist.objects.create(name='Adam')
        self.assertSequenceEqual(Artist.objects.filter(name__iexact='bob'), [bob])

    def test_icontains_lookup(self):
        bob = Artist.objects.create(name='Bob')
        bobby = Artist.objects.create(name='Bobby')
        Artist.objects.create(name='Adam')
        self.assertSequenceEqual(Artist.objects.filter(name__icontains='bo'), [bob, bobby])

    def test_save_existing_object(self):
        bob = Artist.objects.create(name='Bob')
        bob.name = 'bob'
        bob.save()
        self.assertSequenceEqual(Artist.objects.all(), [bob])

    @unittest.expectedFailure
    def test_save_new_object(self):
        # This is difficult to implement - it never hits the queryset.
        bob = Artist(name='Bob')
        bob.save()
        self.assertSequenceEqual(Artist.objects.all(), [bob])

    @unittest.expectedFailure
    def test_delete_object(self):
        # This is difficult to implement - it never hits the queryset.
        bob = Artist.objects.create(name='Bob')
        bob.delete()
        self.assertSequenceEqual(Artist.objects.all(), [])


@no_db_tests
@mock.patch.object(Fan.objects, 'get_queryset', lambda: QuerySet(Fan))
@mock.patch.object(Fan.artist, 'get_queryset', lambda instance: QuerySet(Artist))
@mock.patch.object(Artist.objects, 'get_queryset', lambda: QuerySet(Artist))
@mock.patch.object(Artist.fan_set.related_manager_cls, 'get_queryset', get_related_queryset)
@mock.patch.object(Fan.fan_set.related_manager_cls, 'get_queryset', lambda instance: QuerySet(Fan))
@mock.patch.object(Fan.friends.related_manager_cls, 'get_queryset', get_related_queryset)
@mock.patch.object(Fan.friends.related_manager_cls, '_add_items', add_items)
@mock.patch.object(Fan.friends.related_manager_cls, '_remove_items', remove_items)
@mock.patch.object(Fan.friends.related_manager_cls, '_clear_items', clear_items)
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

    def test_lookups_passed_through(self):
        bob = Artist.objects.create(name='Bob')
        annie = Fan.objects.create(name='Annie', artist=bob)
        dave = Artist.objects.create(name='Dave')
        Fan.objects.create(name='Lottie', artist=dave)
        self.assertSequenceEqual(Fan.objects.filter(artist__name='Bob'), [annie])

    def test_m2m_get_empty(self):
        bob = Artist.objects.create(name='Bob')
        annie = Fan.objects.create(name='Annie', artist=bob)
        self.assertSequenceEqual(annie.friends.all(), [])

    def test_m2m_create(self):
        bob = Artist.objects.create(name='Bob')
        annie = Fan.objects.create(name='Annie', artist=bob)
        lottie = annie.friends.create(name='Lottie', artist=bob)
        self.assertSequenceEqual(annie.friends.all(), [lottie])
        self.assertSequenceEqual(Fan.objects.all(), [annie, lottie])

    def test_m2m_add(self):
        bob = Artist.objects.create(name='Bob')
        annie = Fan.objects.create(name='Annie', artist=bob)
        lottie = Fan.objects.create(name='Lottie', artist=bob)
        annie.friends.add(lottie)
        self.assertSequenceEqual(annie.friends.all(), [lottie])

    def test_m2m_set(self):
        bob = Artist.objects.create(name='Bob')
        annie = Fan.objects.create(name='Annie', artist=bob)
        lottie = Fan.objects.create(name='Lottie', artist=bob)
        annie.friends = [lottie]
        self.assertSequenceEqual(annie.friends.all(), [lottie])
        annie.friends = []
        self.assertSequenceEqual(annie.friends.all(), [])

    def test_m2m_remove(self):
        bob = Artist.objects.create(name='Bob')
        annie = Fan.objects.create(name='Annie', artist=bob)
        lottie = Fan.objects.create(name='Lottie', artist=bob)
        annie.friends = [lottie]
        self.assertSequenceEqual(annie.friends.all(), [lottie])
        annie.friends.remove(lottie)
        self.assertSequenceEqual(annie.friends.all(), [])

