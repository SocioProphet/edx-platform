"""
Decorators for staticbook
"""
from functools import wraps
from urllib.parse import urlparse
from django.conf import settings
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.shortcuts import resolve_url
from lms.djangoapps.courseware.access_utils import check_public_access
from lms.djangoapps.courseware.courses import get_course_by_id
from common.lib.xmodule.xmodule.course_module import COURSE_VISIBILITY_PUBLIC
from opaque_keys.edx.keys import CourseKey


def is_course_public(course_id):
    """
    Check course public status using course_id.
    It returns True if the course is public otherwise it returns False.
    """
    course_key = CourseKey.from_string(course_id)
    course = get_course_by_id(course_key)
    accessResponse = check_public_access(course, [COURSE_VISIBILITY_PUBLIC])
    return accessResponse.has_access


def user_passes_test(test_func, login_url=None, redirect_field_name=REDIRECT_FIELD_NAME):
    """
    Decorator for views that checks that the user passes the given test,
    redirecting to the log-in page if necessary. The test should be a callable
    that takes the user object and a course_id and returns True if the user passes.
    The default test allow authenticated users to pass the test and it only
    allows anonymous users if the course is set to public.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, course_id, *args, **kwargs):
            if test_func(request.user, course_id):
                return view_func(request, course_id, *args, **kwargs)
            path = request.build_absolute_uri()
            resolved_login_url = resolve_url(login_url or settings.LOGIN_URL)
            # If the login url is the same scheme and net location then just
            # use the path as the "next" url.
            login_scheme, login_netloc = urlparse(resolved_login_url)[:2]
            current_scheme, current_netloc = urlparse(path)[:2]
            if ((not login_scheme or login_scheme == current_scheme) and
                    (not login_netloc or login_netloc == current_netloc)):
                path = request.get_full_path()
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(
                path, resolved_login_url, redirect_field_name)
        return _wrapped_view
    return decorator


def allow_anonymous_or_login_required(function=None, redirect_field_name=REDIRECT_FIELD_NAME, login_url=None):
    """
    Decorator for views that checks that the user is logged in or the course is set to public,
    if not it redirects user to the log-in page if necessary.
    """
    actual_decorator = user_passes_test(
        lambda user, course_id : user.is_authenticated or is_course_public(course_id),
        login_url=login_url,
        redirect_field_name=redirect_field_name
    )
    
    if function:
        return actual_decorator(function)
    return actual_decorator
