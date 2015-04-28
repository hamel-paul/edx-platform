"""
Tests for EmbargoMiddleware with CountryAccessRules
"""

import unittest
from mock import patch
import ddt

from django.core.urlresolvers import reverse
from django.conf import settings
from django.core.cache import cache as django_cache

from util.testing import UrlResetMixin
from student.tests.factories import UserFactory
from xmodule.modulestore.tests.factories import CourseFactory
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase
from config_models.models import cache as config_cache

from embargo.models import RestrictedCourse, IPFilter
from embargo.test_utils import restrict_course


@ddt.ddt
@unittest.skipUnless(settings.ROOT_URLCONF == 'lms.urls', 'Test only valid in lms')
class EmbargoMiddlewareAccessTests(UrlResetMixin, ModuleStoreTestCase):
    """Tests of embargo middleware country access rules.

    There are detailed unit tests for the rule logic in
    `test_api.py`; here, we're mainly testing the integration
    with middleware

    """
    USERNAME = 'fred'
    PASSWORD = 'secret'

    @patch.dict(settings.FEATURES, {'EMBARGO': True})
    def setUp(self):
        super(EmbargoMiddlewareAccessTests, self).setUp('embargo')
        self.user = UserFactory(username=self.USERNAME, password=self.PASSWORD)
        self.course = CourseFactory.create()
        self.client.login(username=self.USERNAME, password=self.PASSWORD)

        self.courseware_url = reverse(
            'course_root',
            kwargs={'course_id': unicode(self.course.id)}
        )
        self.non_courseware_url = reverse('dashboard')

        # Clear the cache to avoid interference between tests
        django_cache.clear()
        config_cache.clear()

    @patch.dict(settings.FEATURES, {'EMBARGO': True})
    @ddt.data(True, False)
    def test_blocked(self, disable_access_check):
        with restrict_course(self.course.id, access_point='courseware', disable_access_check=disable_access_check) as redirect_url:  # pylint: disable=line-too-long
            response = self.client.get(self.courseware_url)
            if disable_access_check:
                self.assertEqual(response.status_code, 200)
            else:
                self.assertRedirects(response, redirect_url)

    @patch.dict(settings.FEATURES, {'EMBARGO': True})
    def test_allowed(self):
        # Add the course to the list of restricted courses
        # but don't create any access rules
        RestrictedCourse.objects.create(course_key=self.course.id)

        # Expect that we can access courseware
        response = self.client.get(self.courseware_url)
        self.assertEqual(response.status_code, 200)

    @patch.dict(settings.FEATURES, {'EMBARGO': True})
    def test_non_courseware_url(self):
        with restrict_course(self.course.id):
            response = self.client.get(self.non_courseware_url)
            self.assertEqual(response.status_code, 200)

    @patch.dict(settings.FEATURES, {'EMBARGO': True})
    @ddt.data(
        # request_ip, blacklist, whitelist, is_enabled, allow_access
        ('173.194.123.35', ['173.194.123.35'], [], True, False),
        ('173.194.123.35', ['173.194.0.0/16'], [], True, False),
        ('173.194.123.35', ['127.0.0.0/32', '173.194.0.0/16'], [], True, False),
        ('173.195.10.20', ['173.194.0.0/16'], [], True, True),
        ('173.194.123.35', ['173.194.0.0/16'], ['173.194.0.0/16'], True, False),
        ('173.194.123.35', [], ['173.194.0.0/16'], True, True),
        ('192.178.2.3', [], ['173.194.0.0/16'], True, True),
        ('173.194.123.35', ['173.194.123.35'], [], False, True),
    )
    @ddt.unpack
    def test_ip_access_rules(self, request_ip, blacklist, whitelist, is_enabled, allow_access):
        # Ensure that IP blocking works for anonymous users
        self.client.logout()

        # Set up the IP rules
        IPFilter.objects.create(
            blacklist=", ".join(blacklist),
            whitelist=", ".join(whitelist),
            enabled=is_enabled
        )

        # Check that access is enforced
        response = self.client.get(
            "/",
            HTTP_X_FORWARDED_FOR=request_ip,
            REMOTE_ADDR=request_ip
        )

        if allow_access:
            self.assertEqual(response.status_code, 200)
        else:
            redirect_url = reverse(
                'embargo_blocked_message',
                kwargs={
                    'access_point': 'courseware',
                    'message_key': 'embargo'
                }
            )
            self.assertRedirects(response, redirect_url)

    @patch.dict(settings.FEATURES, {'EMBARGO': True})
    @ddt.data(
        ('courseware', 'default'),
        ('courseware', 'embargo'),
        ('enrollment', 'default'),
        ('enrollment', 'embargo')
    )
    @ddt.unpack
    def test_always_allow_access_to_embargo_messages(self, access_point, msg_key):
        # Blacklist an IP address
        IPFilter.objects.create(
            blacklist="192.168.10.20",
            enabled=True
        )

        url = reverse(
            'embargo_blocked_message',
            kwargs={
                'access_point': access_point,
                'message_key': msg_key
            }
        )
        response = self.client.get(
            url,
            HTTP_X_FORWARDED_FOR="192.168.10.20",
            REMOTE_ADDR="192.168.10.20"
        )
        self.assertEqual(response.status_code, 200)

# TODO:FUNK <<<<<<< HEAD
#         # Accessing a regular course from a non-embargoed IP that's been blacklisted
#         # should succeed
#         response = self.client.get(self.regular_page, HTTP_X_FORWARDED_FOR='5.0.0.0', REMOTE_ADDR='5.0.0.0')
#         self.assertEqual(response.status_code, 200)
# 
#     @ddt.data(
#         (None, False),
#         ("", False),
#         ("us", False),
#         ("CU", True),
#         ("Ir", True),
#         ("sy", True),
#         ("sd", True)
#     )
#     @ddt.unpack
#     def test_embargo_profile_country(self, profile_country, is_embargoed):
#         # Set the country in the user's profile
#         profile = self.user.profile
#         profile.country = profile_country
#         profile.save()
# 
#         # Attempt to access an embargoed course
#         response = self.client.get(self.embargoed_page)
# 
#         # If the user is from an embargoed country, verify that
#         # they are redirected to the embargo page.
#         if is_embargoed:
#             embargo_url = reverse('embargo')
#             self.assertRedirects(response, embargo_url)
# 
#         # Otherwise, verify that the student can access the page
#         else:
#             self.assertEqual(response.status_code, 200)
# 
#         # For non-embargoed courses, the student should be able to access
#         # the page, even if he/she is from an embargoed country.
#         response = self.client.get(self.regular_page)
#         self.assertEqual(response.status_code, 200)
# 
#     def test_embargo_profile_country_cache(self):
#         # Set the country in the user's profile
#         profile = self.user.profile
#         profile.country = "us"
#         profile.save()
# 
#         # Warm the cache
#         with self.assertNumQueries(16):
#             self.client.get(self.embargoed_page)
# 
#         # Access the page multiple times, but expect that we hit
#         # the database to check the user's profile only once
#         with self.assertNumQueries(11):
#             self.client.get(self.embargoed_page)
# 
#     def test_embargo_profile_country_db_null(self):
#         # Django country fields treat NULL values inconsistently.
#         # When saving a profile with country set to None, Django saves an empty string to the database.
#         # However, when the country field loads a NULL value from the database, it sets
#         # `country.code` to `None`.  This caused a bug in which country values created by
#         # the original South schema migration -- which defaulted to NULL -- caused a runtime
#         # exception when the embargo middleware treated the value as a string.
#         # In order to simulate this behavior, we can't simply set `profile.country = None`.
#         # (because when we save it, it will set the database field to an empty string instead of NULL)
#         query = "UPDATE auth_userprofile SET country = NULL WHERE id = %s"
#         connection.cursor().execute(query, [str(self.user.profile.id)])
#         transaction.commit_unless_managed()
# 
#         # Attempt to access an embargoed course
#         # Verify that the student can access the page without an error
#         response = self.client.get(self.embargoed_page)
#         self.assertEqual(response.status_code, 200)
# 
#     @mock.patch.dict(settings.FEATURES, {'EMBARGO': False})
#     def test_countries_embargo_off(self):
#         # When the middleware is turned off, all requests should go through
#         # Accessing an embargoed page from a blocked IP OK
#         response = self.client.get(self.embargoed_page, HTTP_X_FORWARDED_FOR='1.0.0.0', REMOTE_ADDR='1.0.0.0')
#         self.assertEqual(response.status_code, 200)
# 
#         # Accessing a regular page from a blocked IP should succeed
#         response = self.client.get(self.regular_page, HTTP_X_FORWARDED_FOR='1.0.0.0', REMOTE_ADDR='1.0.0.0')
#         self.assertEqual(response.status_code, 200)
# 
#         # Explicitly whitelist/blacklist some IPs
#         IPFilter(
#             whitelist='1.0.0.0',
#             blacklist='5.0.0.0',
#             changed_by=self.user,
# TODO:FUNK =======
    @patch.dict(settings.FEATURES, {'EMBARGO': True})
    def test_whitelist_ip_skips_country_access_checks(self):
        # Whitelist an IP address
        IPFilter.objects.create(
            whitelist="192.168.10.20",
# TODO:FUNK >>>>>>> 00b75f0119b981641833240be214ef2076329747
            enabled=True
        )

        # Set up country access rules so the user would
        # be restricted from the course.
        with restrict_course(self.course.id):
            # Make a request from the whitelisted IP address
            response = self.client.get(
                self.courseware_url,
                HTTP_X_FORWARDED_FOR="192.168.10.20",
                REMOTE_ADDR="192.168.10.20"
            )

        # Expect that we were still able to access the page,
        # even though we would have been blocked by country
        # access rules.
        self.assertEqual(response.status_code, 200)
