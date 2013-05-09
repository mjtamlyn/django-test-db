from django.db.models.constants import LOOKUP_SEP
from django.db.models.query import QuerySet as DjangoQuerySet
from django.utils.tree import Node


data_store = {}


class Query(object):
    """A replacement for Django's sql.Query object.

    Shares a similar API to django.db.models.sql.Query. It has its own data store.
    """
    def __init__(self, model, where=None):
        self.model = model
        data_store.setdefault(model, [])
        self.data_store = data_store[model]
        self.counter = len(self.data_store) + 1
        self.high_mark = None
        self.low_mark = 0
        self.where = []
        self.ordering = None
        self._empty = False

    def execute(self):
        """Execute a query against the data store.

        Work on a copy of the list so we don't accidentally change the store.
        """
        data = self.data_store[:]
        for func in self.where:
            data = filter(func, data)
        if self.ordering:
            data = sorted(data, cmp=self.ordering)
        if self.low_mark and not self.high_mark:
            data = data[self.low_mark:]
        elif self.high_mark:
            data = data[self.low_mark:self.high_mark]
        return data

    def clone(self, *args, **kwargs):
        """Trivial clone method."""
        return self

    def assign_pk(self, obj):
        """Simple counter based "primary key" allocation."""
        obj.pk = self.counter
        self.counter += 1

    def create(self, obj):
        """Creates an object by adding it to the data store.

        Will allocate a PK if one does not exist, but currently does nothing to
        ensure uniqueness of your PKs if you've set one already.
        """
        if not obj.pk:
            self.assign_pk(obj)
        self.data_store.append(obj)

    def delete(self):
        """Removes objects from the data store."""
        items = self.execute()
        for item in items:
            self.data_store.remove(item)

    def update(self, **kwargs):
        """Updates the objects in the data store.

        The correct values may well already have been assigned, espically if
        this triggered by instance.save() rather than queryset.update(), but
        we'll do it again anyway just to be sure.

        Should models be faffing with setattr then this is likely to break
        things.
        """
        data = self.execute()
        for instance in data:
            for key, value in kwargs.items():
                setattr(instance, key, value)
        return len(data)

    def has_results(self, using=None):
        """Find out whether there's anything that matches the current query state."""
        return bool(self.execute())

    def get_count(self, using=None):
        """Find how many objects match the current query state."""
        return len(self.execute())

    def set_limits(self, low=None, high=None):
        """Set limits for query slicing.

        This code is almost identical to Django's code."""
        if high is not None:
            if self.high_mark is not None:
                self.high_mark = min(self.high_mark, self.low_mark + high)
            else:
                self.high_mark = self.low_mark + high
        if low is not None:
            if self.high_mark is not None:
                self.low_mark = min(self.high_mark, self.low_mark + low)
            else:
                self.low_mark = self.low_mark + low

    def can_filter(self):
        """Yeah, we can always filter. Even if Django can't.

        This is probably lies actually, filter + slice is likely broken/weird."""
        return True

    def clear_ordering(self, force_empty=False):
        self.ordering = None

    def set_empty(self):
        self._empty = True

    def is_empty(self):
        return self._empty

    def add_ordering(self, *fields):
        """Create a compare function we can pass to `sorted` when we execute
        the query."""

        def compare(x, y):
            for field in fields:
                reverse = field.startswith('-')
                if reverse:
                    field = field[1:]
                current = cmp(getattr(x, field), getattr(y, field))
                if current is not 0:
                    if reverse:
                        return -current
                    return current
            return 0

        self.ordering = compare

    def add_q(self, q_object):
        """Add filter functions to be used in execute."""
        for child in q_object.children:
            if isinstance(child, Node):
                self.add_q(child)
            else:
                self.where.append(self._get_filter_func(*child, negated=q_object.negated))

    def _get_filter_func(self, key, value, negated=False):
        func = None
        if LOOKUP_SEP in key:
            # This is horribly naive
            key, lookup = key.split(LOOKUP_SEP, 1)
            if lookup == 'exact':
                pass
            elif lookup == 'iexact':
                func = lambda o: value.lower() == getattr(o, key).lower()
            elif lookup == 'contains':
                func = lambda o: value in getattr(o, key)
            elif lookup == 'icontains':
                func = lambda o: value.lower() in getattr(o, key).lower()
            elif lookup == 'in':
                func = lambda o: getattr(o, key) in value
            else:
                next_level_func = self._get_filter_func(lookup, value)
                func = lambda o: next_level_func(getattr(o, key))
        # FIXME: blatantly broken
        if key == 'fan' or key == 'collaborations':
            def func(o):
                try:
                    store = data_store[(self.model, key)]
                except KeyError:
                    return False
                try:
                    list = store[value]
                except KeyError:
                    return False
                return o in list
        if not func:
            func = lambda o: getattr(o, key) == value
        if negated:
            return lambda o: not func(o)
        return func


class QuerySet(DjangoQuerySet):
    """Subclass of Django's QuerySet to simplify some methods.
    
    Generally speaking we try to use Django's qs for most methods, but some
    things are rather more complex than they need to be for our use cases.
    Consequently we simplify the execution functions to just call our Query
    object in a more simple fashion.
    """
    def __init__(self, model=None, query=None, using=None, instance=None):
        query = query or Query(model)
        super(QuerySet, self).__init__(model=model, query=query, using=None)

    def create(self, **kwargs):
        obj = self.model(**kwargs)
        self.query.create(obj)
        return obj

    def get_or_create(self, **kwargs):
        try:
            return self.get(**kwargs), False
        except self.model.DoesNotExist:
            return self.create(**kwargs), True

    def delete(self):
        self.query.delete()

    def update(self, **kwargs):
        return self.query.update(**kwargs)

    def _update(self, values):
        return True

    def iterator(self):
        return iter(self.query.execute())


def get_related_queryset(self):
    """Related querysets are defined funny."""
    return QuerySet(self.model).filter(**self.core_filters)


def add_items(self, source_field_name, target_field_name, *objs):
    """Descriptor method we can attach to the generated RelatedObjectQuerySets."""
    data_store.setdefault((self.model, self.query_field_name), {})
    store = data_store[(self.model, self.query_field_name)]
    store.setdefault(self.instance.id, [])
    store[self.instance.id] += objs


def remove_items(self, source_field_name, target_field_name, *objs):
    """Descriptor method we can attach to the generated RelatedObjectQuerySets."""
    data_store.setdefault((self.model, self.query_field_name), {})
    store = data_store[(self.model, self.query_field_name)]
    store.setdefault(self.instance.id, [])
    for o in objs:
        store[self.instance.id].remove(o)


def clear_items(self, source_field_name):
    """Descriptor method we can attach to the generated RelatedObjectQuerySets."""
    data_store[(self.model, self.query_field_name)] = {}
