import requests

from django.conf import settings

from lms.djangoapps.instructor.access import list_with_level

from lms.djangoapps.courseware.courses import get_course_info_section
from student.models import unique_id_for_user


def send_course_detail_to_ccx_connector(request, course):
    if course.ccx_connector:
        list_staff = list_with_level(course, 'staff')

        course_detail = {
            "title": course.display_name,
            "author_name": None,
            "edx_instance": settings.SITE_NAME,
            "overview": get_course_info_section(request, course, "updates"),
            "video_url": course.course_image,
            "instructors": [unique_id_for_user(staff) for staff in list_staff]
        }

        response = requests.post(
            course.ccx_connector,
            data=course_detail
        )

        print "course_detail: ", course_detail, "response:", response.content
