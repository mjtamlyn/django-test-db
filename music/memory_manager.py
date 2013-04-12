import copy

from django.db.models.constants import LOOKUP_SEP
from django.db.models.query import QuerySet as DjangoQuerySet
from django.utils.tree import Node


data_store = {}


class Query(object):
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
        # shallow copy deliberately
        data = copy.copy(self.data_store)
        for func in self.where:
            data = filter(func, data)
        if self.ordering:
            data = sorted(data, cmp=self.ordering)
        return data

    def clone(self, *args, **kwargs):
        return self

    def assign_pk(self, obj):
        obj.pk = self.counter
        self.counter += 1

    def create(self, obj):
        if not obj.pk:
            self.assign_pk(obj)
        self.data_store.append(obj)

    def delete(self):
        items = self.execute()
        for item in items:
            self.data_store.remove(item)

    def update(self, **kwargs):
        data = self.execute()
        for instance in data:
            for key, value in kwargs.items():
                setattr(instance, key, value)
        return len(data)

    def has_results(self, using=None):
        return bool(self.execute())

    def get_count(self, using=None):
        return len(self.execute())

    def set_limits(self, low=None, high=None):
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
        return True

    def clear_ordering(self, force_empty=False):
        self.ordering = None

    def set_empty(self):
        self._empty = True

    def is_empty(self):
        return self._empty

    def add_ordering(self, *fields):

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
    return QuerySet(self.model).filter(**self.core_filters)


def add_items(self, source_field_name, target_field_name, *objs):
    data_store.setdefault((self.model, self.query_field_name), {})
    store = data_store[(self.model, self.query_field_name)]
    store.setdefault(self.instance.id, [])
    store[self.instance.id] += objs


def remove_items(self, source_field_name, target_field_name, *objs):
    data_store.setdefault((self.model, self.query_field_name), {})
    store = data_store[(self.model, self.query_field_name)]
    store.setdefault(self.instance.id, [])
    for o in objs:
        store[self.instance.id].remove(o)


def clear_items(self, source_field_name):
    data_store[(self.model, self.query_field_name)] = {}
