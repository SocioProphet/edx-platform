__author__ = 'amir'


import datetime
import ddt
import pytz

from nose.plugins.attrib import attr

from courseware.tests.helpers import LoginEnrollmentTestCase
from student.tests.factories import (
    UserFactory
)
from xmodule.modulestore.django import modulestore
from xmodule.modulestore.tests.django_utils import (
    ModuleStoreTestCase,
    SharedModuleStoreTestCase,
    TEST_DATA_SPLIT_MODULESTORE)

from xmodule.modulestore.tests.factories import (
    CourseFactory,
    ItemFactory,
)

from ccx_keys.locator import CCXLocator
from lms.djangoapps.ccx.tests.test_views import flatten


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
                ItemFactory.create(parent=chapter) for _ in xrange(3)
            ] for chapter in cls.chapters
        ])
        cls.verticals = flatten([
            [
                ItemFactory.create(
                    start=start, due=due, parent=sequential, graded=True, format='Homework', category=u'vertical'
                ) for _ in xrange(2)
            ] for sequential in cls.sequentials
        ])

    def setUp(self):
        """
        Set up tests
        """
        super(TestCoachDashboard, self).setUp()

        # Create instructor account
        self.coach = coach = UserFactory.create(password="test")
        self.client.login(username=coach.username, password="test")
        # create an instance of modulestore
        self.store = modulestore()

        with self.store.bulk_operations(self.course.id, emit_signals=False):
            blocks = flatten([  # pylint: disable=unused-variable
                [
                    self.store.create_item(self.coach.id, self.course.id, 'discussion', 'new_component')
                ] for vertical in self.verticals
            ])
