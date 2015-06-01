# coding=UTF-8
"""
Performance tests for field overrides.
"""
import ddt
import mock
from nose.plugins.attrib import attr

from courseware.views import progress  # pylint: disable=import-error
from django.core.cache import cache
from django.test.client import RequestFactory
from django.test.utils import override_settings
from edxmako.middleware import MakoMiddleware  # pylint: disable=import-error
from student.models import CourseEnrollment  # pylint: disable=import-error
from student.tests.factories import UserFactory  # pylint: disable=import-error
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase, \
    TEST_DATA_XML_MODULESTORE, TEST_DATA_SPLIT_MODULESTORE
from xmodule.modulestore.tests.factories import check_mongo_calls
from xmodule.modulestore.xml_importer import import_course_from_xml
from xmodule.tests import DATA_DIR  # pylint: disable=import-error


@attr('shard_1')
@mock.patch.dict(
    'django.conf.settings.FEATURES', {'ENABLE_XBLOCK_VIEW_ENDPOINT': True}
)
@ddt.ddt
class FieldOverridePerformanceTestCase(ModuleStoreTestCase):
    """
    Base class for instrumenting SQL queries and Mongo reads for field override
    providers.
    """
    def setUp(self):
        """
        Create a test client, course, and user.
        """
        super(FieldOverridePerformanceTestCase, self).setUp()

        self.request_factory = RequestFactory()
        self.student = UserFactory.create()
        self.request = self.request_factory.get("foo")
        self.request.user = self.student

        MakoMiddleware().process_request(self.request)

        # TEST_DATA must be overridden by subclasses, otherwise the test is
        # skipped.
        self.TEST_DATA = None

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

    def instrument_course_progress_render(self, course_name, queries, reads):
        """
        Renders the progress page, instrumenting Mongo reads and SQL queries.
        """
        course = self.setup_course(course_name)

        # Clear the cache before measuring
        # TODO: remove once django cache is disabled in tests
        cache.clear()
        with self.assertNumQueries(queries):
            with check_mongo_calls(reads):
                self.grade_course(course)

    def run_if_subclassed(self, test_type, dataset):
        """
        Run the query/read instrumentation only if TEST_DATA has been
        overridden.
        """
        if not self.TEST_DATA:
            self.skipTest(
                "Test not properly configured. TEST_DATA must be overridden "
                "by a subclass."
            )

        queries, reads, course_name = self.TEST_DATA[test_type][dataset]
        self.instrument_course_progress_render(course_name, queries, reads)

    @ddt.data((0,), (1,), (2,))
    @ddt.unpack
    @override_settings(
        FIELD_OVERRIDE_PROVIDERS=(),
    )
    def test_instrument_without_field_override(self, dataset):
        """
        Test without any field overrides.
        """
        self.run_if_subclassed('no_overrides', dataset)

    @ddt.data((0,), (1,), (2,))
    @ddt.unpack
    @override_settings(
        FIELD_OVERRIDE_PROVIDERS=(
                'ccx.overrides.CustomCoursesForEdxOverrideProvider',
        ),
    )
    def test_instrument_with_field_override(self, dataset):
        """
        Test with the CCX field override enabled.
        """
        self.run_if_subclassed('ccx', dataset)


class TestFieldOverrideXmlPerformance(FieldOverridePerformanceTestCase):
    """
    Test cases for instrumenting field overrides against the XML modulestore.
    """
    def setUp(self):
        """
        Set the modulestore and scaffold the test data.
        """
        super(TestFieldOverrideXmlPerformance, self).setUp()

        self.MIDDLEWARE = TEST_DATA_XML_MODULESTORE
        self.TEST_DATA = {
            'no_overrides': [
                (20, 7, 'small'), (24, 7, 'medium'), (28, 7, 'large')
            ],
            'ccx': [
                (20, 24, 'small'), (24, 32, 'medium'), (28, 40, 'large')
            ],
        }


class TestFieldOverrideSplitPerformance(FieldOverridePerformanceTestCase):
    """
    Test cases for instrumenting field overrides against the Split modulestore.
    """
    def setUp(self):
        """
        Set the modulestore and scaffold the test data.
        """
        super(TestFieldOverrideSplitPerformance, self).setUp()

        self.MIDDLEWARE = TEST_DATA_SPLIT_MODULESTORE
        self.TEST_DATA = {
            'no_overrides': [
                (20, 7, 'small'), (24, 7, 'medium'), (28, 7, 'large')
            ],
            'ccx': [
                (20, 24, 'small'), (24, 32, 'medium'), (28, 40, 'large')
            ]
        }
