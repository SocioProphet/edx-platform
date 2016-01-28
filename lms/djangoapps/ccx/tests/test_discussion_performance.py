__author__ = 'amir'


import datetime
import ddt
import pytz
import factory

from nose.plugins.attrib import attr

from ccx_keys.locator import CCXLocator
from courseware.model_data import FieldDataCache
from courseware.module_render import get_module_for_descriptor
from courseware.views import index
from courseware.tests.helpers import LoginEnrollmentTestCase, get_request_for_user
from edxmako.tests import mako_middleware_process_request
from django.core.urlresolvers import reverse
from django.test.client import RequestFactory
from student.tests.factories import (
    CourseEnrollmentFactory,
    UserFactory
)
from xmodule.modulestore.django import modulestore
from xmodule.modulestore.tests.django_utils import (
    ModuleStoreTestCase,
    SharedModuleStoreTestCase,
    TEST_DATA_SPLIT_MODULESTORE
)
from xmodule.modulestore.tests.factories import (
    CourseFactory,
    ItemFactory,
)

from lms.djangoapps.ccx.tests.factories import CcxFactory
from lms.djangoapps.ccx.tests.test_views import flatten
from lms.djangoapps.ccx.utils import ccx_course


@attr('shard_1')
@ddt.ddt
class TestCoachDashboard(SharedModuleStoreTestCase, LoginEnrollmentTestCase):
    """
    Tests for Custom Courses views.
    """
    MODULESTORE = TEST_DATA_SPLIT_MODULESTORE

    @classmethod
    def setUpClass(cls):
        super(TestCoachDashboard, cls).setUpClass()
        cls.course = course = CourseFactory.create()

        # Create a course outline
        cls.mooc_start = start = datetime.datetime(
            2010, 5, 12, 2, 42, tzinfo=pytz.UTC
        )
        cls.mooc_due = due = datetime.datetime(
            2010, 7, 7, 0, 0, tzinfo=pytz.UTC
        )

        cls.chapters = [
            ItemFactory.create(start=start, parent=course) for _ in xrange(2)
        ]
        cls.sequentials = flatten([
            [
                ItemFactory.create(start=start, due=due, parent=chapter) for _ in xrange(3)
            ] for chapter in cls.chapters
        ])
        cls.verticals = flatten([
            [
                ItemFactory.create(
                    start=start, due=due, parent=sequential, graded=True, format='Homework', category=u'vertical'
                ) for _ in xrange(2)
            ] for sequential in cls.sequentials
        ])

        with cls.store.bulk_operations(course.id, emit_signals=False):
            blocks = flatten([  # pylint: disable=unused-variable
                [
                    ItemFactory.create(
                        parent_location=vertical.location,
                        category="discussion",
                        discussion_id= factory.Sequence(u'discussion{0}'.format),
                        display_name=factory.Sequence(u'discussion{0}'.format),
                        discussion_category="Chapter",
                        discussion_target=factory.Sequence(u'discussion{0}'.format),
                    )
                ] for vertical in cls.verticals
            ])

    def setUp(self):
        """
        Set up tests
        """
        super(TestCoachDashboard, self).setUp()
        # Create instructor account
        self.coach = coach = UserFactory.create(password="test")
        CourseEnrollmentFactory(user=coach, course_id=self.course.id)
        self.client.login(username=coach.username, password="test")
        # create an instance of modulestore
        self.store = modulestore()

    def make_ccx(self):
        """
        create ccx
        """
        ccx = CcxFactory(course_id=self.course.id, coach=self.coach)
        return ccx

    def test_query_count_on_load_courseware_ccx(self):
        ccx = self.make_ccx()
        ccx_locator = CCXLocator.from_course_locator(self.course.id, ccx.id)

        request = get_request_for_user(self.coach)
        mako_middleware_process_request(request)

        with self.assertNumQueries(14):
            with ccx_course(ccx_locator) as course:
                with modulestore().bulk_operations(course.id):
                    field_data_cache = FieldDataCache.cache_for_descriptor_descendents(
                        course.id, request.user, course, depth=2
                    )
                    course_module = get_module_for_descriptor(
                        self.coach, request, course, field_data_cache, course.id, course=course
                    )
                    chapters = course_module.get_display_items()

                    request = RequestFactory().get(
                        reverse(
                            'courseware_section',
                            kwargs={
                                'course_id': unicode(ccx_locator),
                                'chapter': chapters[0].url_name,
                                'section': chapters[0].get_display_items()[0].url_name,
                            }
                        )
                    )
                    request.user = self.coach
                    mako_middleware_process_request(request)
                    index(
                        request,
                        unicode(course.id),
                        chapter=chapters[0].url_name,
                        section=chapters[0].get_display_items()[0].url_name
                    )

    def test_query_count_on_load_courseware(self):
        request = RequestFactory().get(
            reverse(
                'courseware_section',
                kwargs={
                    'course_id': unicode(self.course.id),
                    'chapter': self.chapters[0].url_name,
                    'section': self.sequentials[0].url_name,
                }
            )
        )
        request.user = self.coach
        mako_middleware_process_request(request)

        with self.assertNumQueries(53):
            index(
                request,
                unicode(self.course.id),
                chapter=self.chapters[0].url_name,
                section=self.sequentials[0].url_name
            )
