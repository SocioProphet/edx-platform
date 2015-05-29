# coding=UTF-8
"""
tests for overrides
"""
import datetime
import ddt
import mock
import pytz
from nose.plugins.attrib import attr

from courseware.field_overrides import OverrideFieldData  # pylint: disable=import-error
from courseware.views import progress  # pylint: disable=import-error
from django.core import cache
from django.test.client import RequestFactory
from django.test.utils import override_settings
from edxmako.middleware import MakoMiddleware  # pylint: disable=import-error
from student.models import CourseEnrollment  # pylint: disable=import-error
from student.tests.factories import AdminFactory, UserFactory  # pylint: disable=import-error
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase, \
    TEST_DATA_XML_MODULESTORE
from xmodule.modulestore.tests.factories import CourseFactory, ItemFactory, \
    check_mongo_calls
from xmodule.modulestore.xml_importer import import_course_from_xml
from xmodule.tests import DATA_DIR  # pylint: disable=import-error

from ..models import CustomCourseForEdX
from ..overrides import override_field_for_ccx

from .test_views import flatten, iter_blocks


@attr('shard_1')
@override_settings(FIELD_OVERRIDE_PROVIDERS=(
    'ccx.overrides.CustomCoursesForEdxOverrideProvider',))
class TestFieldOverrides(ModuleStoreTestCase):
    """
    Make sure field overrides behave in the expected manner.
    """
    def setUp(self):
        """
        Set up tests
        """
        super(TestFieldOverrides, self).setUp()
        self.course = course = CourseFactory.create()

        # Create a course outline
        self.mooc_start = start = datetime.datetime(
            2010, 5, 12, 2, 42, tzinfo=pytz.UTC)
        self.mooc_due = due = datetime.datetime(
            2010, 7, 7, 0, 0, tzinfo=pytz.UTC)
        chapters = [ItemFactory.create(start=start, parent=course)
                    for _ in xrange(2)]
        sequentials = flatten([
            [ItemFactory.create(parent=chapter) for _ in xrange(2)]
            for chapter in chapters])
        verticals = flatten([
            [ItemFactory.create(due=due, parent=sequential) for _ in xrange(2)]
            for sequential in sequentials])
        blocks = flatten([  # pylint: disable=unused-variable
            [ItemFactory.create(parent=vertical) for _ in xrange(2)]
            for vertical in verticals])

        self.ccx = ccx = CustomCourseForEdX(
            course_id=course.id,
            display_name='Test CCX',
            coach=AdminFactory.create())
        ccx.save()

        patch = mock.patch('ccx.overrides.get_current_ccx')
        self.get_ccx = get_ccx = patch.start()
        get_ccx.return_value = ccx
        self.addCleanup(patch.stop)

        # Apparently the test harness doesn't use LmsFieldStorage, and I'm not
        # sure if there's a way to poke the test harness to do so.  So, we'll
        # just inject the override field storage in this brute force manner.
        OverrideFieldData.provider_classes = None
        for block in iter_blocks(course):
            block._field_data = OverrideFieldData.wrap(   # pylint: disable=protected-access
                AdminFactory.create(), block._field_data)   # pylint: disable=protected-access

        def cleanup_provider_classes():
            """
            After everything is done, clean up by un-doing the change to the
            OverrideFieldData object that is done during the wrap method.
            """
            OverrideFieldData.provider_classes = None
        self.addCleanup(cleanup_provider_classes)

    def test_override_start(self):
        """
        Test that overriding start date on a chapter works.
        """
        ccx_start = datetime.datetime(2014, 12, 25, 00, 00, tzinfo=pytz.UTC)
        chapter = self.course.get_children()[0]
        override_field_for_ccx(self.ccx, chapter, 'start', ccx_start)
        self.assertEquals(chapter.start, ccx_start)

    def test_override_num_queries(self):
        """
        Test that overriding and accessing a field produce same number of queries.
        """
        ccx_start = datetime.datetime(2014, 12, 25, 00, 00, tzinfo=pytz.UTC)
        chapter = self.course.get_children()[0]
        with self.assertNumQueries(4):
            override_field_for_ccx(self.ccx, chapter, 'start', ccx_start)
            dummy = chapter.start

    def test_overriden_field_access_produces_no_extra_queries(self):
        """
        Test no extra queries when accessing an overriden field more than once.
        """
        ccx_start = datetime.datetime(2014, 12, 25, 00, 00, tzinfo=pytz.UTC)
        chapter = self.course.get_children()[0]
        with self.assertNumQueries(4):
            override_field_for_ccx(self.ccx, chapter, 'start', ccx_start)
            dummy1 = chapter.start
            dummy2 = chapter.start
            dummy3 = chapter.start

    def test_override_is_inherited(self):
        """
        Test that sequentials inherit overridden start date from chapter.
        """
        ccx_start = datetime.datetime(2014, 12, 25, 00, 00, tzinfo=pytz.UTC)
        chapter = self.course.get_children()[0]
        override_field_for_ccx(self.ccx, chapter, 'start', ccx_start)
        self.assertEquals(chapter.get_children()[0].start, ccx_start)
        self.assertEquals(chapter.get_children()[1].start, ccx_start)

    def test_override_is_inherited_even_if_set_in_mooc(self):
        """
        Test that a due date set on a chapter is inherited by grandchildren
        (verticals) even if a due date is set explicitly on grandchildren in
        the mooc.
        """
        ccx_due = datetime.datetime(2015, 1, 1, 00, 00, tzinfo=pytz.UTC)
        chapter = self.course.get_children()[0]
        chapter.display_name = 'itsme!'
        override_field_for_ccx(self.ccx, chapter, 'due', ccx_due)
        vertical = chapter.get_children()[0].get_children()[0]
        self.assertEqual(vertical.due, ccx_due)


@attr('shard_1')
@mock.patch.dict('django.conf.settings.FEATURES', {'ENABLE_XBLOCK_VIEW_ENDPOINT': True})
@ddt.ddt
class TestFieldOverridePerformance(ModuleStoreTestCase):
    """
    Tests that ensure the field
    """
    def setUp(self):
        """
        Create a test client, course, and user.
        """
        super(TestFieldOverridePerformance, self).setUp()

        self.request_factory = RequestFactory()
        self.student = UserFactory.create()
        self.request = self.request_factory.get("foo")
        self.request.user = self.student

        MakoMiddleware().process_request(self.request)

    def setup_course(self, course_name):
        """
        Imports some XML course data.
        """
        course = import_course_from_xml(
            self.store,
            999,
            DATA_DIR,
            ['test_increasing_size/graded_{}'.format(course_name)]
        )[0]

        CourseEnrollment.enroll(self.student, course.id)

        return course

    def grade_course(self, course):
        """
        Renders the progress page for the given course.
        """
        return progress(
            self.request,
            course_id=course.id.to_deprecated_string(),
            student_id=self.student.id
        )

    def instrument_course_grading(self, course_name, queries, reads):
        """
        Renders the progress page, instrumenting Mongo reads and SQL queries.
        """
        course = self.setup_course(course_name)

        # Disable the cache
        # TODO: remove once django cache is disabled in tests
        single_thread_dummy_cache = cache.get_cache(
            backend='django.core.cache.backends.dummy.DummyCache',
            LOCATION='single_thread_local_cache'
        )
        single_thread_dummy_cache.clear()
        with self.assertNumQueries(queries):
            with check_mongo_calls(reads):
                self.grade_course(course)
        single_thread_dummy_cache.clear()

    TEST_DATA = {
        'xml': {
            'no_overrides': [
                (19, 7, 'small'), (23, 7, 'medium'), (27, 7, 'large')
            ],
            'ccx': [
                (19, 24, 'small'), (23, 32, 'medium'), (27, 40, 'large')
            ]
        },
        'split': {
            'no_overrides': [
                (19, 7, 'small'), (23, 7, 'medium'), (27, 7, 'large')
            ],
            'ccx': [
                (20, 24, 'small'), (23, 32, 'medium'), (27, 40, 'large')
            ]
        }
    }

    @ddt.data(*TEST_DATA['xml']['no_overrides'])
    @ddt.unpack
    @override_settings(
        FIELD_OVERRIDE_PROVIDERS=(),
        MODULESTORE=TEST_DATA_XML_MODULESTORE
    )
    def test_instrument_without_field_override_xml(self, queries, reads, course_name):
        """
        Test without any field overrides on XML.
        """
        self.instrument_course_grading(course_name, queries, reads)

    @ddt.data(*TEST_DATA['xml']['ccx'])
    @ddt.unpack
    @override_settings(
        FIELD_OVERRIDE_PROVIDERS=('ccx.overrides.CustomCoursesForEdxOverrideProvider',),
        MODULESTORE=TEST_DATA_XML_MODULESTORE
    )
    def test_instrument_with_field_override_xml(self, queries, reads, course_name):
        """
        Test with the CCX field override on XML.
        """
        self.instrument_course_grading(course_name, queries, reads)

    @ddt.data(*TEST_DATA['split']['no_overrides'])
    @ddt.unpack
    @override_settings(
        FIELD_OVERRIDE_PROVIDERS=(),
    )
    def test_instrument_without_field_override_split(self, queries, reads, course_name):
        """
        Test without any field overrides on Split.
        """
        self.instrument_course_grading(course_name, queries, reads)

    @ddt.data(*TEST_DATA['split']['ccx'])
    @ddt.unpack
    @override_settings(
        FIELD_OVERRIDE_PROVIDERS=('ccx.overrides.CustomCoursesForEdxOverrideProvider',),
    )
    def test_instrument_with_field_override_split(self, queries, reads, course_name):
        """
        Test with the CCX field override on Split.
        """
        self.instrument_course_grading(course_name, queries, reads)
