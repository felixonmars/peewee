import datetime
import logging
import unittest

import peewee
from peewee import SelectQuery, InsertQuery, UpdateQuery, DeleteQuery, database


class QueryLogHandler(logging.Handler):
    def __init__(self, *args, **kwargs):
        self.queries = []
        logging.Handler.__init__(self, *args, **kwargs)
        
    def emit(self, record):
        self.queries.append(record)


# test models
class Blog(peewee.Model):
    title = peewee.CharField()
    
    def __unicode__(self):
        return self.title


class Entry(peewee.Model):
    title = peewee.CharField(max_length=50)
    content = peewee.TextField()
    pub_date = peewee.DateTimeField()
    blog = peewee.ForeignKeyField(Blog)
    
    def __unicode__(self):
        return '%s: %s' % (self.blog.title, self.title)


class EntryTag(peewee.Model):
    tag = peewee.CharField(max_length=50)
    entry = peewee.ForeignKeyField(Entry)
    
    def __unicode__(self):
        return self.tag


class User(peewee.Model):
    username = peewee.CharField(max_length=50)
    blog = peewee.ForeignKeyField(Blog, null=True)


class BasePeeweeTestCase(unittest.TestCase):
    def setUp(self):
        database.connect()
        Blog.create_table()
        Entry.create_table()
        EntryTag.create_table()
        User.create_table()
        
        self.qh = QueryLogHandler()
        peewee.logger.setLevel(logging.DEBUG)
        peewee.logger.addHandler(self.qh)
    
    def tearDown(self):
        peewee.logger.removeHandler(self.qh)
        
        User.drop_table()
        EntryTag.drop_table()
        Entry.drop_table()
        Blog.drop_table()
        database.close()
    
    def queries(self):
        return [x.msg for x in self.qh.queries]
    
    def assertQueriesEqual(self, queries):
        self.assertEqual(queries, self.queries())
    
    def create_blog(self, **kwargs):
        blog = Blog(**kwargs)
        blog.save()
        return blog
    
    def create_entry(self, **kwargs):
        entry = Entry(**kwargs)
        entry.save()
        return entry
    
    def create_entry_tag(self, **kwargs):
        entry_tag = EntryTag(**kwargs)
        entry_tag.save()
        return entry_tag


class QueryTests(BasePeeweeTestCase):
    def test_select(self):
        sq = SelectQuery(peewee.database, Blog, '*')
        self.assertEqual(sq.sql(), 'SELECT * FROM blog')
        
        sq = SelectQuery(peewee.database, Blog, '*').where(title='a')
        self.assertEqual(sq.sql(), 'SELECT * FROM blog WHERE title = "a"')
        self.assertEqual(sq._where, {Blog: {'title': '= "a"'}})
        
        sq = SelectQuery(peewee.database, Blog, '*').where(title='a').where(id=1)
        self.assertEqual(sq._where, {Blog: {'title': '= "a"', 'id': '= 1'}})
        
        sq = SelectQuery(peewee.database, Blog, '*').where(title__in=['a', 'b'])
        self.assertEqual(sq.sql(), 'SELECT * FROM blog WHERE title IN ("a","b")')
        self.assertEqual(sq._where, {Blog: {'title': 'IN ("a","b")'}})
    
    def test_selecting_across_joins(self):
        sq = SelectQuery(peewee.database, Entry, '*').where(title='a1').join(Blog).where(title='a')
        self.assertEqual(sq._where, {
            Entry: {'title': '= "a1"'},
            Blog: {'title': '= "a"'}
        })
        self.assertEqual(sq._joins, [Blog])
        self.assertEqual(sq.sql(), 'SELECT t1.* FROM entry AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id WHERE t1.title = "a1" AND t2.title = "a"')
        
        sq = SelectQuery(peewee.database, Blog, '*').join(Entry).where(title='a1')        
        self.assertEqual(sq._where, {
            Entry: {'title': '= "a1"'}
        })
        self.assertEqual(sq._joins, [Entry])
        self.assertEqual(sq.sql(), 'SELECT t1.* FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id WHERE t2.title = "a1"')

        sq = SelectQuery(peewee.database, EntryTag, '*').join(Entry).join(Blog).where(title='a')        
        self.assertEqual(sq._where, {
            Blog: {'title': '= "a"'}
        })
        self.assertEqual(sq._joins, [Entry, Blog])
        self.assertEqual(sq.sql(), 'SELECT t1.* FROM entrytag AS t1 INNER JOIN entry AS t2 ON t1.entry_id = t2.id\nINNER JOIN blog AS t3 ON t2.blog_id = t3.id WHERE t3.title = "a"')
        
        sq = SelectQuery(peewee.database, Blog, '*').join(Entry).join(EntryTag).where(tag='t2')
        self.assertEqual(sq._where, {
            EntryTag: {'tag': '= "t2"'}
        })
        self.assertEqual(sq._joins, [Entry, EntryTag])
        self.assertEqual(sq.sql(), 'SELECT t1.* FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id\nINNER JOIN entrytag AS t3 ON t2.id = t3.entry_id WHERE t3.tag = "t2"')
    
    def test_selecting_with_aggregation(self):
        sq = SelectQuery(peewee.database, Blog, 't1.*, COUNT(t2.id) AS count').join(Entry).group_by('t1.id')
        self.assertEqual(sq._where, {})
        self.assertEqual(sq._joins, [Entry])
        self.assertEqual(sq.sql(), 'SELECT t1.*, COUNT(t2.id) AS count FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id GROUP BY t1.id')
        
        sq = sq.having('count > 2')
        self.assertEqual(sq.sql(), 'SELECT t1.*, COUNT(t2.id) AS count FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id GROUP BY t1.id HAVING count > 2')
    
    def test_selecting_with_ordering(self):        
        sq = SelectQuery(peewee.database, Blog).order_by('title')
        self.assertEqual(sq.sql(), 'SELECT * FROM blog ORDER BY title ASC')
        
        sq = SelectQuery(peewee.database, Blog).order_by(peewee.desc('title'))
        self.assertEqual(sq.sql(), 'SELECT * FROM blog ORDER BY title DESC')
        
        sq = SelectQuery(peewee.database, Entry).order_by(peewee.desc('title')).join(Blog).where(title='a')
        self.assertEqual(sq.sql(), 'SELECT t1.* FROM entry AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id WHERE t2.title = "a" ORDER BY t1.title DESC')
        
        sq = SelectQuery(peewee.database, Entry).join(Blog).order_by(peewee.desc('title'))
        self.assertEqual(sq.sql(), 'SELECT t1.* FROM entry AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id ORDER BY t2.title DESC')

    def test_ordering_on_aggregates(self):
        sq = SelectQuery(
            peewee.database, Blog, 't1.*, COUNT(t2.id) as count'
        ).join(Entry).order_by(peewee.desc('count'))
        self.assertEqual(sq.sql(), 'SELECT t1.*, COUNT(t2.id) as count FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id ORDER BY count DESC')

    def test_insert(self):
        iq = InsertQuery(peewee.database, Blog, title='a')
        self.assertEqual(iq.sql(), 'INSERT INTO blog (title) VALUES ("a")')
        self.assertEqual(iq.execute(), 1)
        
        iq = InsertQuery(peewee.database, Blog, title='b')
        self.assertEqual(iq.sql(), 'INSERT INTO blog (title) VALUES ("b")')
        self.assertEqual(iq.execute(), 2)
    
    def test_update(self):
        iq = InsertQuery(peewee.database, Blog, title='a').execute()
        
        uq = UpdateQuery(peewee.database,Blog, title='A').where(id=1)
        self.assertEqual(uq.sql(), 'UPDATE blog SET title="A" WHERE id = 1')
        self.assertEqual(uq.execute(), 1)
        
        iq2 = InsertQuery(peewee.database, Blog, title='b').execute()
        
        uq = UpdateQuery(peewee.database, Blog, title='B').where(id=2)
        self.assertEqual(uq.sql(), 'UPDATE blog SET title="B" WHERE id = 2')
        self.assertEqual(uq.execute(), 1)
        
        sq = SelectQuery(peewee.database, Blog).order_by('id')
        self.assertEqual([x.title for x in sq], ['A', 'B'])
    
    def test_delete(self):
        InsertQuery(peewee.database, Blog, title='a').execute()
        InsertQuery(peewee.database, Blog, title='b').execute()
        InsertQuery(peewee.database, Blog, title='c').execute()
        
        dq = DeleteQuery(peewee.database, Blog).where(title='b')
        self.assertEqual(dq.sql(), 'DELETE FROM blog WHERE title = "b"')
        self.assertEqual(dq.execute(), 1)
        
        sq = SelectQuery(peewee.database, Blog).order_by('id')
        self.assertEqual([x.title for x in sq], ['a', 'c'])
        
        dq = DeleteQuery(peewee.database, Blog)
        self.assertEqual(dq.sql(), 'DELETE FROM blog')
        self.assertEqual(dq.execute(), 2)
        
        sq = SelectQuery(peewee.database, Blog).order_by('id')
        self.assertEqual([x.title for x in sq], [])
    
    def test_count(self):
        for i in xrange(10):
            self.create_blog(title='a%d' % i)
        
        count = SelectQuery(peewee.database, Blog).count()
        self.assertEqual(count, 10)
        
        count = Blog.select().count()
        self.assertEqual(count, 10)
        
        for blog in SelectQuery(peewee.database, Blog):
            for i in xrange(20):
                self.create_entry(title='entry%d' % i, blog=blog)
        
        count = SelectQuery(peewee.database, Entry).count()
        self.assertEqual(count, 200)
        
        count = SelectQuery(peewee.database, Entry).join(Blog).where(title="a0").count()
        self.assertEqual(count, 20)
        
        count = SelectQuery(peewee.database, Entry).where(
            title__icontains="0"
        ).join(Blog).where(
            title="a5"
        ).count()
        self.assertEqual(count, 2)
    
    def test_pagination(self):
        sq = SelectQuery(peewee.database, Blog).paginate(1, 20)
        self.assertEqual(sq.sql(), 'SELECT * FROM blog LIMIT 20 OFFSET 0')
        
        sq = SelectQuery(peewee.database, Blog).paginate(3, 30)
        self.assertEqual(sq.sql(), 'SELECT * FROM blog LIMIT 30 OFFSET 60')
    
    def test_inner_joins(self):
        sql = SelectQuery(peewee.database, Blog).join(Entry).sql()
        self.assertEqual(sql, 'SELECT t1.* FROM blog AS t1 INNER JOIN entry AS t2 ON t1.id = t2.blog_id')
        
        sql = SelectQuery(peewee.database, Entry).join(Blog).sql()
        self.assertEqual(sql, 'SELECT t1.* FROM entry AS t1 INNER JOIN blog AS t2 ON t1.blog_id = t2.id')

    def test_outer_joins(self):
        sql = SelectQuery(peewee.database, User).join(Blog).sql()
        self.assertEqual(sql, 'SELECT t1.* FROM user AS t1 LEFT OUTER JOIN blog AS t2 ON t1.blog_id = t2.id')
        
        sql = SelectQuery(peewee.database, Blog).join(User).sql()
        self.assertEqual(sql, 'SELECT t1.* FROM blog AS t1 LEFT OUTER JOIN user AS t2 ON t1.id = t2.blog_id')


class ModelTests(BasePeeweeTestCase):
    def test_model_save(self):
        a = self.create_blog(title='a')
        self.assertEqual(a.id, 1)
        
        b = self.create_blog(title='b')
        self.assertEqual(b.id, 2)
        
        a.save()
        b.save()
        
        self.assertQueriesEqual([
            'INSERT INTO blog (title) VALUES ("a")',
            'INSERT INTO blog (title) VALUES ("b")',
            'UPDATE blog SET title="a" WHERE id = 1',
            'UPDATE blog SET title="b" WHERE id = 2'
        ])

        all_blogs = list(Blog.select().order_by('id'))
        self.assertEqual(all_blogs, [a, b])
    
    def test_model_get(self):
        a = self.create_blog(title='a')
        b = self.create_blog(title='b')
        
        b2 = Blog.get(title='b')
        self.assertEqual(b2.id, b.id)
        
        self.assertQueriesEqual([
            'INSERT INTO blog (title) VALUES ("a")',
            'INSERT INTO blog (title) VALUES ("b")',
            'SELECT * FROM blog WHERE title = "b" LIMIT 1 OFFSET 0'
        ])
    
    def test_model_select(self):
        a = self.create_blog(title='a')
        b = self.create_blog(title='b')
        c = self.create_blog(title='c')
        
        qr = Blog.select().order_by('title')
        self.assertEqual(list(qr), [a, b, c])
        
        qr = Blog.select().where(title__in=['a', 'c']).order_by(peewee.desc('title'))
        self.assertEqual(list(qr), [c, a])
        
        self.assertQueriesEqual([
            'INSERT INTO blog (title) VALUES ("a")', 
            'INSERT INTO blog (title) VALUES ("b")', 
            'INSERT INTO blog (title) VALUES ("c")', 
            'SELECT * FROM blog ORDER BY title ASC', 
            'SELECT * FROM blog WHERE title IN ("a","c") ORDER BY title DESC'
        ])
    
    def test_query_results_wrapper(self):
        a = self.create_blog(title='a')
        b = self.create_blog(title='b')
        
        qr = Blog.select().order_by('title').execute()
        self.assertFalse(qr._populated)
        
        blogs = [b for b in qr]
        self.assertEqual(blogs, [a, b])
        self.assertTrue(qr._populated)
        
        self.assertQueriesEqual([
            'INSERT INTO blog (title) VALUES ("a")', 
            'INSERT INTO blog (title) VALUES ("b")', 
            'SELECT * FROM blog ORDER BY title ASC'
        ])
        
        blogs = [b for b in qr]
        self.assertEqual(blogs, [a, b])
        
        self.assertEqual(len(self.queries()), 3)
        
        blogs = [b for b in qr]
        self.assertEqual(blogs, [a, b])
        
        self.assertEqual(len(self.queries()), 3)
    
    def test_select_caching(self):
        a = self.create_blog(title='a')
        b = self.create_blog(title='b')
        
        sq = Blog.select().order_by('title')
        blogs = [b for b in sq]
        self.assertEqual(blogs, [a, b])
        
        self.assertQueriesEqual([
            'INSERT INTO blog (title) VALUES ("a")', 
            'INSERT INTO blog (title) VALUES ("b")', 
            'SELECT * FROM blog ORDER BY title ASC'
        ])
        
        self.assertFalse(sq._dirty)

        blogs = [b for b in sq]
        self.assertEqual(blogs, [a, b])
        self.assertEqual(len(self.queries()), 3)
        
        # mark dirty
        sq = sq.where(title='a')
        self.assertTrue(sq._dirty)
        
        blogs = [b for b in sq]
        self.assertEqual(blogs, [a])
        
        self.assertQueriesEqual([
            'INSERT INTO blog (title) VALUES ("a")', 
            'INSERT INTO blog (title) VALUES ("b")', 
            'SELECT * FROM blog ORDER BY title ASC',
            'SELECT * FROM blog WHERE title = "a" ORDER BY title ASC'
        ])
        
        blogs = [b for b in sq]
        self.assertEqual(blogs, [a])
        
        self.assertEqual(len(self.queries()), 4)


class RelatedFieldTests(BasePeeweeTestCase):
    def get_common_objects(self):
        a = self.create_blog(title='a')
        a1 = self.create_entry(title='a1', content='a1', blog=a)
        a2 = self.create_entry(title='a2', content='a2', blog=a)
        
        b = self.create_blog(title='b')
        b1 = self.create_entry(title='b1', content='b1', blog=b)
        b2 = self.create_entry(title='b2', content='b2', blog=b)
        
        t1 = self.create_entry_tag(tag='t1', entry=a2)
        t2 = self.create_entry_tag(tag='t2', entry=b2)
        return a, a1, a2, b, b1, b2, t1, t2
    
    def test_fk_caching(self):
        a = self.create_blog(title='a')
        e = self.create_entry(title='e', blog=a)
        
        self.assertEqual(e.blog, a)
        self.assertEqual(e.blog, a)
        
        self.assertQueriesEqual([
            'INSERT INTO blog (title) VALUES ("a")', 
            'INSERT INTO entry (content,blog_id,pub_date,title) VALUES ("",1,NULL,"e")'
        ])
        
        e2 = Entry.get(id=e.id)
        self.assertEqual(e2.blog, a)
        self.assertEqual(e2.blog, a)
        
        self.assertQueriesEqual([
            'INSERT INTO blog (title) VALUES ("a")', 
            'INSERT INTO entry (content,blog_id,pub_date,title) VALUES ("",1,NULL,"e")',
            'SELECT * FROM entry WHERE id = 1 LIMIT 1 OFFSET 0',
            'SELECT * FROM blog WHERE id = 1'
        ])
    
    def test_foreign_keys(self):
        a, a1, a2, b, b1, b2, t1, t2 = self.get_common_objects()
        
        self.assertEqual(len(self.queries()), 8)
        
        self.assertEqual(a1.blog, a)
        self.assertNotEqual(a1.blog, b)
        
        self.assertEqual(a1.blog_id, a.id)
        
        self.assertEqual(b1.blog, b)
        self.assertEqual(b1.blog_id, b.id)
        
        self.assertEqual(t1.entry.blog, a)
        self.assertEqual(t2.entry.blog, b)
        
        # no queries!
        self.assertEqual(len(self.queries()), 8)
        
        t = EntryTag.get(id=t1.id)
        self.assertEqual(t.entry.blog, a)
        self.assertEqual(t.entry.blog, a)
        
        # just 3, tag select, entry select, blog select
        self.assertEqual(len(self.queries()), 11)
        
        a3 = Entry(title='a3', content='a3')
        a3.blog = a
        self.assertEqual(a3.blog, a)
        self.assertEqual(a3.blog_id, a.id)
        
        a3.save()
        self.assertEqual(a3.blog, a)
        self.assertEqual(a3.blog_id, a.id)
        
        a3.blog = b
        self.assertEqual(a3.blog, b)
        self.assertEqual(a3.blog_id, b.id)
        
        a3.save()
        self.assertEqual(a3.blog, b)
        self.assertEqual(a3.blog_id, b.id)
    
    def test_reverse_fk(self):
        a, a1, a2, b, b1, b2, t1, t2 = self.get_common_objects()
        
        self.assertEqual(list(a.entry_set), [a1, a2])
        
        self.assertEqual(list(a.entry_set.where(title='a1')), [a1])
        
        self.assertEqual(list(a1.entrytag_set), [])
        self.assertEqual(list(a2.entrytag_set), [t1])
    
    def test_querying_across_joins(self):
        a, a1, a2, b, b1, b2, t1, t2 = self.get_common_objects()
        
        sq = Blog.select().join(Entry).join(EntryTag).where(tag='t1')
        self.assertEqual(list(sq), [a])
        
        sq = Blog.select().join(Entry).join(EntryTag).where(tag='t2')
        self.assertEqual(list(sq), [b])
        
        sq = Blog.select().join(Entry).where(title='a1').join(EntryTag).where(tag='t1')
        self.assertEqual(list(sq), [])
        
        sq = Blog.select().join(Entry).where(title='a2').join(EntryTag).where(tag='t1')
        self.assertEqual(list(sq), [a])
        
        sq = EntryTag.select().join(Entry).join(Blog).where(title='a')
        self.assertEqual(list(sq), [t1])
        
        sq = EntryTag.select().join(Entry).join(Blog).where(title='b')
        self.assertEqual(list(sq), [t2])
        
        sq = EntryTag.select().join(Entry).where(title='a1').join(Blog).where(title='a')
        self.assertEqual(list(sq), [])
        
        sq = EntryTag.select().join(Entry).where(title='a2').join(Blog).where(title='a')
        self.assertEqual(list(sq), [t1])

    def test_ordering_across_joins(self):
        a, a1, a2, b, b1, b2, t1, t2 = self.get_common_objects()
        b3 = self.create_entry(title='b3', blog=b)
        c = self.create_blog(title='c')
        c1 = self.create_entry(title='c1', blog=c)

        sq = Blog.select().join(Entry).order_by(peewee.desc('title')).group_by('t1.id')
        self.assertEqual(list(sq), [c, b, a])

        sq = Blog.select().where(title__in=['a', 'b']).join(Entry).order_by(peewee.desc('title')).group_by('t1.id')
        self.assertEqual(list(sq), [b, a])

        sq = Blog.select('t1.*, COUNT(t2.id) AS count').join(Entry).order_by(peewee.desc('count')).group_by('t1.id')
        qr = list(sq)

        self.assertEqual(qr, [b, a, c])
        self.assertEqual(qr[0].count, 3)
        self.assertEqual(qr[1].count, 2)
        self.assertEqual(qr[2].count, 1)


class FieldTypeTests(BasePeeweeTestCase):
    def jd(self, d):
        return datetime.datetime(2010, 1, d)
    
    def create_common(self):
        b = self.create_blog(title='dummy')
        self.create_entry(title='b1', content='b1', pub_date=self.jd(1), blog=b)
        self.create_entry(title='b2', content='b2', pub_date=self.jd(2), blog=b)
        self.create_entry(title='b3', content='b3', pub_date=self.jd(3), blog=b)
    
    def assertSQEqual(self, sq, lst):
        self.assertEqual(sorted([x.title for x in sq]), sorted(lst))
        
    def test_lookups_charfield(self):
        self.create_common()
        
        self.assertSQEqual(Entry.select().where(title__gt='b1'), ['b2', 'b3'])
        self.assertSQEqual(Entry.select().where(title__gte='b2'), ['b2', 'b3'])
        
        self.assertSQEqual(Entry.select().where(title__lt='b3'), ['b1', 'b2'])
        self.assertSQEqual(Entry.select().where(title__lte='b2'), ['b1', 'b2'])
        
        self.assertSQEqual(Entry.select().where(title__icontains='b'), ['b1', 'b2', 'b3'])
        self.assertSQEqual(Entry.select().where(title__icontains='2'), ['b2'])
        
        self.assertSQEqual(Entry.select().where(title__contains='b'), ['b1', 'b2', 'b3'])
        
        self.assertSQEqual(Entry.select().where(title__in=['b1', 'b3']), ['b1', 'b3'])
        self.assertSQEqual(Entry.select().where(title__in=[]), [])
    
    def test_lookups_datefield(self):
        self.create_common()
        
        self.assertSQEqual(Entry.select().where(pub_date__gt=self.jd(1)), ['b2', 'b3'])
        self.assertSQEqual(Entry.select().where(pub_date__gte=self.jd(2)), ['b2', 'b3'])
        
        self.assertSQEqual(Entry.select().where(pub_date__lt=self.jd(3)), ['b1', 'b2'])
        self.assertSQEqual(Entry.select().where(pub_date__lte=self.jd(2)), ['b1', 'b2'])
        
        self.assertSQEqual(Entry.select().where(pub_date__in=[self.jd(1), self.jd(3)]), ['b1', 'b3'])
        self.assertSQEqual(Entry.select().where(pub_date__in=[]), [])