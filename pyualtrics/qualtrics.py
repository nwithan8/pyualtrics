#!/usr/bin/env python3


# TODO: Exceptions for 401 Unauthorized API responses


import csv
import io
import zipfile
from datetime import datetime
import pandas as pd
import requests
import time
import logging

logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.INFO)



header: str = ""
verboseRequests: bool = False


def _compare_timestamps(stamp1, stamp2, beforeAfter=None):
    if not beforeAfter or beforeAfter.lower()[0] not in ['b', 'a']:
        raise Exception("before/after not specified")
    stamp1 = datetime.strptime(stamp1, "%Y-%m-%d %H:%M:%S")
    stamp2 = datetime.strptime(stamp2, "%Y-%m-%d %H:%M:%S")
    if beforeAfter == 'b':
        return stamp1 > stamp2
    if beforeAfter == 'a':
        return stamp1 < stamp2
    return None


def get_request(url, request_header=None, payload: dict = None, stream: bool = False):
    if verboseRequests:
        logging.info("GET {}".format(url))
    return requests.get(url, headers=(request_header if request_header else header), data=payload, stream=stream)


def post_request(url, request_header=None, payload: dict = None):
    if verboseRequests:
        logging.info("POST {}".format(url))
    return requests.post(url, headers=(request_header if request_header else header), json=payload)


def put_request(url, request_header=None, payload: dict = None):
    if verboseRequests:
        logging.info("PUT {}".format(url))
    return requests.put(url, headers=(request_header if request_header else header), json=payload)


def delete_request(url, request_header=None):
    if verboseRequests:
        logging.info("DELETE {}".format(url))
    return requests.delete(url, headers=(request_header if request_header else header))


class PermissionSet:
    def __init__(self, data):
        self.data = data
        self.permissions = []
        self._get_permissions(self.data)

    def _get_permissions(self, data):
        for k, v in data.items():
            self.permissions.append(Permission(permission_type=k, data=v))


class Qualtrics:
    def __init__(self, qualtricsUrl: str, qualtricsToken: str, surveyResponseFolder: str = None,
                 skipAPICalls: bool = True, verbose: bool = False):
        """

        :param qualtricsUrl: Your organizational base URL (likely https://yourorganization.qualtrics.com/API/v3)
        :param qualtricsToken: Your Qualtrics API key
        :param surveyResponseFolder: Where survey responses should be downloaded to
        :param skipAPICalls:
        False: Make several Qualtrics API calls to create all object attributes.
            Responses CSV files will be downloaded for every survey in your organization.
        True: Certain attributes will have to be manually called from the API at a later time
            (i.e. Qualtrics.get_surveys(), Qualtrics.get_users())
        """
        global header, verboseRequests
        self.baseUrl = qualtricsUrl
        self.token = qualtricsToken
        self.header = {'X-API-TOKEN': self.token}
        header = self.header
        verboseRequests = verbose
        self.skipAPICalls = skipAPICalls
        self.responseFolder = surveyResponseFolder
        self.surveys = []
        self.users = []
        self.mailing_lists = []
        self.libraries = []
        self.groups = []
        if not self.skipAPICalls:  # will trigger a bunch of API calls, including downloading results files for every survey
            self.get_surveys()
            self.get_users()
            self.get_mailing_lists()
            self.get_libraries()
            self.get_groups()

    def who_am_i(self, skipAPICalls: bool = False):
        res = get_request('{baseUrl}/whoami'.format(baseUrl=self.baseUrl))
        if res:
            return User(data=res.json()['result'], qualtrics=self, skipAPICalls=skipAPICalls)
        return None

    def get_organization(self, organization_id: str, skipAPICalls: bool = False):
        res = get_request('{baseUrl}/organizations/{org_id}'.format(baseUrl=self.baseUrl, org_id=organization_id))
        if res:
            return Organization(data=res.json['result'], qualtrics=self, skipAPICalls=skipAPICalls)
        return None

    def get_division(self, division_id: str, skipAPICalls: bool = False):
        res = get_request('{baseUrl}/organizations/{div_id}'.format(baseUrl=self.baseUrl, div_id=division_id))
        if res:
            return Division(data=res.json['result'], qualtrics=self, skipAPICalls=skipAPICalls)
        return None

    def create_division(self, division_name: str, admin_user_id: list = None, permissions: PermissionSet = None,
                        returnNewDivision: bool = True, skipAPICalls: bool = False):
        data = {'name': division_name}
        if admin_user_id:
            data['divisionAdmins'] = [user for user in admin_user_id]
        if permissions:
            data['permissions'] = permissions.data
        res = post_request(url='{}/divisions'.format(self.baseUrl), payload=data)
        if res:
            if returnNewDivision:
                new_division_id = res.json()['result']['id']
                return self.get_division(division_id=new_division_id, skipAPICalls=skipAPICalls)
            return True
        if returnNewDivision:
            return None
        return False

    def get_groups(self, _carriedGroups=None, _offset=0, forceUpdate: bool = False, skipAPICalls: bool = False):
        if forceUpdate or not self.surveys:
            time.sleep(1)  # have to wait for API server to catch up
            groups = []
            if _carriedGroups:
                groups = _carriedGroups
            res = get_request(
                url='{}/groups{}'.format(self.baseUrl, "?offset={}".format(_offset) if _offset > 0 else ""))
            if res:
                for group in res.json()['result']['elements']:
                    groups.append(Group(data=groups, qualtrics=self, skipAPICalls=skipAPICalls))
                if res.json()['result'].get('nextPage'):
                    groups = self.get_groups(_carriedGroups=groups,
                                             _offset=_offset + int(res.json()['result'].get('nextPage')),
                                             forceUpdate=forceUpdate,
                                             skipAPICalls=skipAPICalls)
            self.groups = groups
        return self.groups

    def get_group(self, group_id: str = None, group_name: str = None, forceUpdate: bool = False,
                  skipAPICalls: bool = False):
        if not group_id and not group_name:
            return None
        groups = self.get_groups(forceUpdate=forceUpdate, skipAPICalls=skipAPICalls)
        if groups:
            for group in groups:
                if group_id and group_id == group.id:
                    return group
                if group_name and group_name == group.name:
                    return group
        return None

    def create_group(self, group_type: str, group_name: str, division_id: str = None, returnNewGroup: bool = True,
                     skipAPICalls: bool = False):
        data = {'type': group_type,
                'name': group_name}
        if division_id:
            data['divisionId'] = division_id
        res = post_request(url='{}/groups'.format(self.baseUrl), payload=data)
        if res:
            self.get_groups(forceUpdate=True, skipAPICalls=skipAPICalls)
            if returnNewGroup:
                new_group_id = res.json()['result']['id']
                return self.get_group(group_id=new_group_id, skipAPICalls=skipAPICalls)
            return True
        if returnNewGroup:
            return None
        return False

    def get_surveys(self, _carriedSurveys=None, _offset=0, forceUpdate: bool = False, skipAPICalls: bool = False):
        if forceUpdate or not self.surveys:
            time.sleep(1)  # have to wait for API server to catch up
            surveys = []
            if _carriedSurveys:
                surveys = _carriedSurveys
            res = get_request(
                url='{}/surveys{}'.format(self.baseUrl, "?offset={}".format(_offset) if _offset > 0 else ""))
            if res:
                for survey in res.json()['result']['elements']:
                    surveys.append(Survey(data=survey, qualtrics=self, responseFolder=self.responseFolder,
                                          skipAPICalls=skipAPICalls))
                if res.json()['result'].get('nextPage'):
                    surveys = self.get_surveys(_carriedSurveys=surveys,
                                               _offset=_offset + 100,
                                               forceUpdate=forceUpdate,
                                               skipAPICalls=skipAPICalls)
            self.surveys = surveys
        return self.surveys

    def get_survey(self, survey_id: str = None, survey_name: str = None, forceUpdate: bool = False,
                   skipAPICalls: bool = False):
        if not survey_id and not survey_name:
            return None
        surveys = self.get_surveys(forceUpdate=forceUpdate, skipAPICalls=skipAPICalls)
        if surveys:
            for survey in surveys:
                if survey_id and survey_id == survey.id:
                    return survey
                if survey_name and survey_name == survey.name:
                    return survey
        return None

    def get_survey_details(self, survey_id: str = None, survey_name: str = None, skipAPICalls: bool = False):
        if not survey_id and not survey_name:
            return None
        if not survey_id:
            survey = self.get_survey(survey_name=survey_name, skipAPICalls=skipAPICalls)
            if survey:
                survey_id = survey.id
            else:
                return None
        res = get_request(url='{}/survey-definitions/{}'.format(self.baseUrl, survey_id))
        if res:
            return res.json()['result']
        return None

    def get_users(self, forceUpdate: bool = False, skipAPICalls: bool = False):
        if forceUpdate or not self.users:
            time.sleep(1)  # have to wait for API server to catch up
            users = []
            res = get_request(url='{}/users'.format(self.baseUrl))
            if res:
                for user in res.json()['result']['elements']:
                    users.append(User(data=user, qualtrics=self, skipAPICalls=False))
            else:
                return None
            self.users = users
        return self.users

    def get_user(self, user_id: str = None, user_username: str = None, forceUpdate: bool = False,
                 skipAPICalls: bool = False):
        if not user_id and not user_username:
            return None
        users = self.get_users(forceUpdate=forceUpdate, skipAPICalls=skipAPICalls)
        if users:
            for user in users:
                if user_id and user_id == user.id:
                    return user
                if users and user_username == user.username:
                    return user
        return None

    def create_user(self,
                    username: str,
                    firstName: str,
                    lastName: str,
                    userType: str,
                    email: str,
                    password: str,
                    language: str = 'en',
                    timeZone: str = None,
                    divisionId: str = None,
                    accountExpirationDate: datetime = None,
                    returnNewUser: bool = True,
                    skipAPICalls: bool = False):
        data = {"username": username,
                "password": password,
                "firstName": firstName,
                "lastName": lastName,
                "userType": userType,
                "email": email,
                "language": language}
        if timeZone:
            data['timeZone'] = timeZone
        if divisionId:
            data['divisionId'] = divisionId
        if accountExpirationDate:
            data['accountExpirationDate'] = accountExpirationDate
        res = post_request(url='{}/users'.format(self.baseUrl), payload=data)
        if res:
            self.get_users(forceUpdate=True, skipAPICalls=skipAPICalls)
            if returnNewUser:
                new_user_id = res.json()['result']['id']
                return self.get_user(user_id=new_user_id, skipAPICalls=skipAPICalls)
            return True
        if returnNewUser:
            return None
        return False

    def get_mailing_lists(self, _carriedLists=None, _offset=0, forceUpdate: bool = False, skipAPICalls: bool = False):
        if forceUpdate or not self.mailing_lists:
            time.sleep(1)  # have to wait for API server to catch up
            lists = []
            if _carriedLists:
                lists = _carriedLists
            res = get_request(
                url='{}/mailinglists{}'.format(self.baseUrl, "?offset={}".format(_offset) if _offset > 0 else ""))
            if res:
                for mailing_list in res.json()['result']['elements']:
                    lists.append(MailingList(data=mailing_list, qualtrics=self, skipAPICalls=skipAPICalls))
                if res.json()['result'].get('nextPage'):
                    lists = self.get_mailing_lists(_carriedLists=lists,
                                                   _offset=_offset + int(res.json()['result'].get('nextPage')),
                                                   forceUpdate=forceUpdate,
                                                   skipAPICalls=skipAPICalls)
            self.mailing_lists = lists
        return self.mailing_lists

    def get_mailing_list(self, list_id=None, list_name=None, forceUpdate: bool = False, skipAPICalls: bool = False):
        if not list_id and not list_name:
            return None
        lists = self.get_mailing_lists(forceUpdate=forceUpdate, skipAPICalls=skipAPICalls)
        if lists:
            for mailing_list in lists:
                if list_id and list_id == mailing_list.id:
                    return mailing_list
                if list_name and list_name == mailing_list.name:
                    return mailing_list
        return None

    def create_mailing_list(self, list_name: str, library_id: str, entries_to_add: dict = None,
                            list_category: str = None,
                            returnNewList: bool = True, skipAPICalls: bool = False):
        data = {'libraryId': library_id,
                'name': list_name}
        if list_category:
            data['category'] = list_category
        res = post_request(url='{}/mailinglists'.format(self.baseUrl), payload=data)
        if res:
            new_list_id = res.json()['result']['id']
            self.get_mailing_lists(forceUpdate=True, skipAPICalls=skipAPICalls)
            if returnNewList or entries_to_add:
                new_list = self.get_mailing_list(list_id=new_list_id, skipAPICalls=skipAPICalls)
                if entries_to_add:
                    for entry in entries_to_add:
                        new_list.create_contact(entry_data=entry, returnNewContact=False, skipAPICalls=skipAPICalls)
                if returnNewList:
                    return new_list
            return True
        if returnNewList:
            return None
        return False

    def get_libraries(self, _carriedLibraries=None, _nextPageURL=None, forceUpdate: bool = False,
                      skipAPICalls: bool = False):
        if forceUpdate or not self.libraries:
            time.sleep(1)  # have to wait for API server to catch up
            libraries = []
            if _carriedLibraries:
                libraries = _carriedLibraries
            url = '{baseUrl}/libraries'.format(baseUrl=self.baseUrl)
            if _nextPageURL:
                url = _nextPageURL
            res = get_request(url=url)
            if res:
                for library in res.json()['result']['elements']:
                    libraries.append(Library(data=library, qualtrics=self, skipAPICalls=skipAPICalls))
                if res.json()['result'].get('nextPage'):
                    libraries = self.get_libraries(_carriedLibraries=libraries,
                                                   _nextPageURL=res.json()['result'].get('nextPage'),
                                                   forceUpdate=forceUpdate,
                                                   skipAPICalls=skipAPICalls)
            self.libraries = libraries
        return self.libraries

    def get_library(self, library_name: str = None, library_id: str = None, forceUpdate: bool = False,
                    skipAPICalls: bool = False):
        if not library_id and not library_name:
            return None
        libraries = self.get_libraries(forceUpdate=forceUpdate, skipAPICalls=skipAPICalls)
        if libraries:
            for library in libraries:
                if library_id and library_id == library.id:
                    return library
                if library_name and library_name == library.name:
                    return library
        return None


class Organization:
    def __init__(self, data, qualtrics: Qualtrics, skipAPICalls: bool = False):
        self.data = data
        self.qualtrics = qualtrics
        self.id = data.get('id')
        self.name = data.get('name')
        self.baseUrl = data.get('baseUrl')
        self.type = data.get('type')
        self.status = data.get('status')
        self.creationDate = data.get('creationDate')
        self.expirationDate = data.get('expirationDate')
        self.stats = data.get('stats')


class Division:
    def __init__(self, data, qualtrics: Qualtrics, skipAPICalls: bool = False):
        self.data = data
        self.qualtrics = qualtrics
        self.id = data.get('id')
        self.name = data.get('name')
        self.organizationId = data.get('organizationId')
        self.organization = None
        if not skipAPICalls:
            self.organization = qualtrics.get_organization(organization_id=self.organizationId,
                                                           skipAPICalls=skipAPICalls)
        self.creationDate = data.get('creationDate')
        self.creatorId = data.get('creatorId')
        self.permissions = PermissionSet(data.get('permissions'))
        self.responseCounts = data.get('responseCounts')
        self.status = data.get('status')

    def update(self,
               name: str = None,
               status: str = None,
               permissions: PermissionSet = None,
               returnNewDivision: bool = True,
               skipAPICalls: bool = False):
        data = {}
        for var, varname in [
            [name, 'name'],
            [status, 'status']
        ]:
            if var:
                data[varname] = var
        if permissions:
            data['permissions'] = permissions.data
        res = put_request('{baseUrl}/divisions/{d_id}'.format(baseUrl=self.qualtrics.baseUrl, d_id=self.id),
                          payload=data)
        if res:
            if returnNewDivision:
                return self.qualtrics.get_division(division_id=self.id, skipAPICalls=skipAPICalls)
            return True
        if returnNewDivision:
            return None
        return False


class Library:
    def __init__(self, data, qualtrics: Qualtrics, skipAPICalls: bool = False):
        self.data = data
        self.qualtrics = qualtrics
        self.id = data.get('libraryId')
        self.name = data.get('libraryName')
        self.surveys = []
        if not skipAPICalls:
            self.get_surveys()

    def get_surveys(self, _carriedSurveys=None, _nextPageURL=None, forceUpdate: bool = False,
                    skipAPICalls: bool = False):
        if forceUpdate or not self.surveys:
            time.sleep(1)  # have to wait for API server to catch up
            surveys = []
            if _carriedSurveys:
                surveys = _carriedSurveys
            url = '{baseUrl}/libraries/{l_id}/survey/surveys'.format(baseUrl=self.qualtrics.baseUrl, l_id=self.id)
            if _nextPageURL:
                url = _nextPageURL
            res = get_request(url=url)
            if res:
                for survey in res.json()['result']['elements']:
                    surveys.append(
                        Survey(data=survey, qualtrics=self.qualtrics, responseFolder=self.qualtrics.responseFolder,
                               skipAPICalls=skipAPICalls))
                if res.json()['result'].get('nextPage'):
                    surveys = self.get_surveys(_carriedSurveys=surveys,
                                               _nextPageURL=res.json()['result'].get('nextPage'),
                                               forceUpdate=forceUpdate,
                                               skipAPICalls=skipAPICalls)
            self.surveys = surveys
        return self.surveys

    def get_survey(self, survey_id=None, survey_name=None, forceUpdate: bool = False, skipAPICalls: bool = False):
        if not survey_id and not survey_name:
            return None
        surveys = self.get_surveys(forceUpdate=forceUpdate, skipAPICalls=skipAPICalls)
        if surveys:
            for survey in surveys:
                if survey_id and survey_id == survey.id:
                    return survey
                if survey_name and survey_name == survey.name:
                    return survey
        return None


class MailingList:
    def __init__(self, data, qualtrics: Qualtrics, skipAPICalls: bool = False):
        self.data = data
        self.qualtrics = qualtrics
        self.libraryId = data.get('libraryId')
        self.id = data.get('id')
        self.name = data.get('name')
        self.category = data.get('category')
        self.folder = data.get('folder')
        self.contacts = []
        if not skipAPICalls:
            self.get_contacts()

    def update(self,
               libraryId: str = None,
               name: str = None,
               category: str = None,
               returnNewList: bool = True,
               skipAPICalls: bool = False):
        data = {}
        for var, varname in [
            [libraryId, 'libraryId'],
            [name, 'name'],
            [category, 'category']
        ]:
            if var:
                data[varname] = var
        res = put_request('{baseUrl}/mailinglists/{list_id}'.format(baseUrl=self.qualtrics.baseUrl, list_id=self.id),
                          payload=data)
        if res:
            self.qualtrics.get_mailing_lists(forceUpdate=True, skipAPICalls=skipAPICalls)
            if returnNewList:
                return self.qualtrics.get_mailing_list(list_id=self.id, skipAPICalls=skipAPICalls)
            return True
        if returnNewList:
            return None
        return False

    def delete(self, skipAPICalls: bool = False):
        res = delete_request(url=
                             '{baseUrl}/mailinglists/{list_id}/'.format(baseUrl=self.qualtrics.baseUrl,
                                                                        list_id=self.id))
        if res:
            self.qualtrics.get_mailing_lists(forceUpdate=True, skipAPICalls=skipAPICalls)
            return True
        return False

    def get_contacts(self, _carriedContacts=None, _nextPageURL=None, forceUpdate: bool = False,
                     skipAPICalls: bool = False):
        if forceUpdate or not self.contacts:
            time.sleep(1)  # have to wait for API server to catch up
            contacts = []
            if _carriedContacts:
                contacts = _carriedContacts
            url = '{baseUrl}/mailinglists/{list_id}/contacts'.format(baseUrl=self.qualtrics.baseUrl, list_id=self.id)
            if _nextPageURL:
                url = _nextPageURL
            res = get_request(url=url)
            if res:
                for contact in res.json()['result']['elements']:
                    contacts.append(
                        Contact(data=contact, mailingList=self, qualtrics=self.qualtrics, skipAPICalls=skipAPICalls))
                if res.json()['result'].get('nextPage'):
                    contacts = self.get_contacts(_carriedContacts=contacts,
                                                 _nextPageURL=res.json()['result'].get('nextPage'),
                                                 forceUpdate=forceUpdate,
                                                 skipAPICalls=skipAPICalls)
            self.contacts = contacts
        return self.contacts

    def get_contact(self, contact_name: dict = None, contact_id: str = None, forceUpdate: bool = False,
                    skipAPICalls: bool = False):
        if not contact_name and not contact_id:
            return None
        for k in ['firstName', 'lastName']:
            if k not in contact_name.keys():
                return None
        contacts = self.get_contacts(forceUpdate=forceUpdate, skipAPICalls=skipAPICalls)
        if contacts:
            for contact in contacts:
                if contact_id and contact_id == contact.id:
                    return contact
                if contact_name and contact_name['firstName'] == contact.firstName and contact_name[
                    'lastName'] == contact.lastName:
                    return contact
        return None

    def create_contact(self,
                       entry_data: dict = None,
                       firstName: str = None,
                       lastName: str = None,
                       email: str = None,
                       externalDataRef: str = None,
                       language: str = None,
                       unsubscribed: bool = False,
                       embeddedData: dict = None,
                       returnNewContact: bool = True,
                       skipAPICalls: bool = False):
        if not entry_data:
            entry_data = {}
            for var, varname in [
                [firstName, 'firstName'],
                [lastName, 'lastName'],
                [email, 'email'],
                [externalDataRef, 'externalDataRef'],
                [language, 'language'],
                [embeddedData, 'embeddedData']
            ]:
                if var:
                    entry_data[varname] = var
            if unsubscribed is not None:
                entry_data['unsubscribed'] = unsubscribed
        res = post_request(
            '{baseUrl}/mailinglists/{list_id}/contacts'.format(baseUrl=self.qualtrics.baseUrl, list_id=self.id),
            payload=entry_data)
        if res:
            self.get_contacts(forceUpdate=True, skipAPICalls=skipAPICalls)
            if returnNewContact:
                return self.get_contact(contact_id=res.json()['result']['id'], skipAPICalls=skipAPICalls)
            return True
        if returnNewContact:
            return None
        return False


class Contact:
    def __init__(self, data, mailingList: MailingList, qualtrics: Qualtrics, skipAPICalls: bool = False):
        self.data = data
        self.mailingList = mailingList
        self.qualtrics = qualtrics
        self.id = data.get('id')
        self.firstName = data.get('firstName')
        self.lastName = data.get('lastName')
        self.email = data.get('email')
        self.externalDataReference = data.get('externalDataReference')
        self.embeddedData = data.get('embeddedData')
        self.language = data.get('language')
        self.unsubscribed = data.get('unsubscribed')
        self.responseHistory = data.get('responseHistory')
        self.emailHistory = data.get('emailHistory')

    def update(self,
               firstName: str = None,
               lastName: str = None,
               email: str = None,
               externalDataRef: str = None,
               language: str = None,
               unsubscribed: bool = False,
               embeddedData: dict = None,
               returnNewContact: bool = True,
               skipAPICalls: bool = False):
        data = {}
        for var, varname in [
            [firstName, 'firstName'],
            [lastName, 'lastName'],
            [email, 'email'],
            [externalDataRef, 'externalDataRef'],
            [language, 'language'],
            [embeddedData, 'embeddedData']
        ]:
            if var:
                data[varname] = var
        if unsubscribed is not None:
            data['unsubscribed'] = unsubscribed
        res = put_request(url='{baseUrl}/mailinglists/{list_id}/contacts/{c_id}'.format(baseUrl=self.qualtrics.baseUrl,
                                                                                        list_id=self.mailingList.id,
                                                                                        c_id=self.id),
                          payload=data)
        if res:
            self.mailingList.get_contacts(forceUpdate=True, skipAPICalls=skipAPICalls)
            if returnNewContact:
                return self.mailingList.get_contact(contact_id=self.id, skipAPICalls=skipAPICalls)
            return True
        if returnNewContact:
            return None
        return False

    def delete(self, skipAPICalls: bool = False):
        res = delete_request(
            url='{baseUrl}/mailinglists/{list_id}/contacts/{c_id}'.format(baseUrl=self.qualtrics.baseUrl,
                                                                          list_id=self.mailingList.id,
                                                                          c_id=self.id))
        if res:
            self.mailingList.get_contacts(forceUpdate=True, skipAPICalls=skipAPICalls)
            return True
        return False


class Permission:
    def __init__(self, data, permission_type=None):
        self.data = data
        self.type = permission_type


class User:
    def __init__(self, data, qualtrics: Qualtrics, skipAPICalls: bool = False):
        self.data = data
        self.qualtrics = qualtrics
        self.id = data.get('id')
        if data.get('userId'):
            self.id = data.get('userId')
        self.username = data.get('userName')
        self.email = data.get('email')
        self.firstName = data.get('firstName')
        self.lastName = data.get('lastName')
        self.userType = data.get('userType')
        self.brandId = data.get('brandId')
        self.organizationId = data.get('organizationId')
        self.divisionId = data.get('divisionId')
        self.language = data.get('language')
        self.accountType = data.get('accountType')
        self.accountStatus = data.get('accountStatus')
        self.accountExpirationDate = data.get('accountExpirationDate')
        if not skipAPICalls:
            self.permissions = PermissionSet(data.get('permissions'))

    def _construct_permissions_dict(self, permissionSet=None):
        if not permissionSet:
            permissionSet = self.permissions
        permission_dict = {}
        for permission in permissionSet.permissions:
            permission_dict[permission.type] = permission.data
        return permission_dict

    def update(self,
               username: str = None,
               firstName: str = None,
               lastName: str = None,
               userType: str = None,
               status: str = None,
               email: str = None,
               language: str = None,
               timeZone: str = None,
               divisionId: str = None,
               accountExpirationDate: datetime = None,
               permissions: PermissionSet = None,
               returnNewUser: bool = True,
               skipAPICalls: bool = False):
        data = {}
        for var, varname in [
            [username, 'username'],
            [firstName, 'firstName'],
            [lastName, 'lastName'],
            [userType, 'userType'],
            [divisionId, 'divisionId'],
            [status, 'status'],
            [language, 'language'],
            [timeZone, 'timeZone'],
            [accountExpirationDate, 'accountExpirationDate'],
            [email, 'email']]:
            if var:
                data[varname] = var
        if permissions:
            data['permissions'] = self._construct_permissions_dict(permissionSet=permissions)
        res = put_request(self.qualtrics.baseUrl, payload=data)
        if res:
            self.qualtrics.get_users(forceUpdate=True, skipAPICalls=skipAPICalls)
            if returnNewUser:
                return self.qualtrics.get_user(user_id=self.id, skipAPICalls=skipAPICalls)
            return True
        if returnNewUser:
            return None
        return False

    def delete(self, skipAPICalls: bool = False):
        res = delete_request(url=
                             '{baseUrl}/users/{u_id}'.format(baseUrl=self.qualtrics.baseUrl, u_id=self.id))
        if res:
            self.qualtrics.get_users(forceUpdate=True, skipAPICalls=skipAPICalls)
            return True
        return False

    def get_api_token(self, skipAPICalls: bool = False):
        res = get_request(
            url='{baseUrl}/users/{id}/apitoken'.format(baseUrl=self.qualtrics.baseUrl, id=self.id))
        if res:
            return res.json()['result']['apiToken']
        return None

    def create_api_token(self, skipAPICalls: bool = False):
        res = post_request(
            url='{baseUrl}/users/{id}/apitoken'.format(baseUrl=self.qualtrics.baseUrl, id=self.id))
        if res:
            return res.json()['result']['apiToken']
        return None


class Group:
    def __init__(self, data, qualtrics: Qualtrics, skipAPICalls: bool = False):
        self.data = data
        self.qualtrics = qualtrics
        self.id = data.get('id')
        self.name = data.get('name')

    def update(self,
               name: str = None,
               group_type: str = None,
               division_id: str = None,
               returnNewGroup: bool = True,
               skipAPICalls: bool = False):
        data = {}
        for var, varname in [
            [name, 'name'],
            [group_type, 'status'],
            [division_id, 'divisionId']
        ]:
            if var:
                data[varname] = var
        res = put_request('{baseUrl}/groups/{g_id}'.format(baseUrl=self.qualtrics.baseUrl, g_id=self.id),
                          payload=data)
        if res:
            self.qualtrics.get_groups(forceUpdate=True, skipAPICalls=skipAPICalls)
            if returnNewGroup:
                return self.qualtrics.get_group(group_id=self.id, skipAPICalls=skipAPICalls)
            return True
        if returnNewGroup:
            return None
        return False

    def delete(self, skipAPICalls: bool = False):
        res = delete_request(url=
                             '{baseUrl}/groups/{g_id}'.format(baseUrl=self.qualtrics.baseUrl, g_id=self.id))
        if res:
            self.qualtrics.get_groups(forceUpdate=True, skipAPICalls=skipAPICalls)
            return True
        return False

    def add_user(self, user: User = None, user_id: str = None, skipAPICalls: bool = False):
        if not user and not user_id:
            return False
        data = {'userId': user_id}
        if user:
            data['userId'] = user.id
        res = post_request(url=
                           '{baseUrl}/groups/{g_id}/members'.format(baseUrl=self.qualtrics.baseUrl, g_id=self.id),
                           payload=data)
        if res:
            return True
        return False

    def remove_user(self, user: User = None, user_id: str = None, skipAPICalls: bool = False):
        if not user and not user_id:
            return False
        if user:
            user_id = user.id
        res = delete_request(url=
                             '{baseUrl}/groups/{g_id}/members/{u_id}'.format(baseUrl=self.qualtrics.baseUrl,
                                                                             g_id=self.id, u_id=user_id))
        if res:
            return True
        return False


class Choice:
    def __init__(self, data, choiceNumber, skipAPICalls: bool = False):
        self.data = data
        self.number = choiceNumber
        self.text = data.get('Display')
        self.graphicSize = data.get('GraphicSize')
        self.image = None
        if data.get('Image'):
            self.image = Image(data.get('Image'))


class Survey:
    def __init__(self, data, qualtrics: Qualtrics, responseFolder, responseFile: str = None,
                 skipAPICalls: bool = False):
        self.json = data
        self.qualtrics = qualtrics
        self.id = data.get('id')
        self.name = data.get('name')
        self.owner = data.get('ownerId')
        if self.owner and not skipAPICalls:
            self.owner = qualtrics.get_user(user_id=self.owner)
        self.organizationId = data.get('organizationId')
        self.active = data.get('isActive')
        self.creationDate = data.get('creationDate')
        self.lastModifiedDate = data.get('lastModifiedDate')
        self.expiration = data.get('expiration')
        self.responseFolder = responseFolder
        self.responsesFile = responseFile
        self.questions = []
        self.responses = []
        self.quotas = []
        self.flow = None
        if self.responsesFile and not skipAPICalls:
            self.get_responses()
        if not skipAPICalls:
            self.get_questions()
            self.get_quotas()
            self.get_flow()
        self.responseDataframe = self._create_responses_dataframe()

    def _export_survey(self,
                       fileFormat,
                       folderName=None,
                       start_date=None,
                       end_date=None,
                       limit=None,
                       use_labels=None,
                       seen_unanswered_recode=None,
                       multiselect_seen_unanswered_recode=None,
                       include_display_order=None,
                       format_decimal_as_comma=None,
                       time_zone=None,
                       newline_replacement=None,
                       question_ids=None,
                       embedded_data_ids=None,
                       survey_metadata_ids=None,
                       compress=None):
        if not folderName and not self.responseFolder:
            raise Exception('No response folder assigned')
        if not folderName:
            folderName = self.responseFolder
        self.responseFolder = folderName
        downloadStatus = "inProgress"

        # create request headers and data
        header = {
            "content-type": "application/json",
            "x-api-token": self.qualtrics.token,
        }
        data = {'format': fileFormat}
        for var, varname in [
            [start_date, 'startDate'],
            [end_date, 'endDate'],
            [limit, 'limit'],
            [use_labels, 'useLabels'],
            [seen_unanswered_recode, 'seenUnansweredRecode'],
            [multiselect_seen_unanswered_recode, 'multiselectSeenUnansweredRecode'],
            [include_display_order, 'includeDisplayOrder'],
            [format_decimal_as_comma, 'formatDecimalAsComma'],
            [time_zone, 'timeZone'],
            [newline_replacement, 'newlineReplacement'],
            [question_ids, 'questionIds'],
            [embedded_data_ids, 'embeddedDataIds'],
            [survey_metadata_ids, 'surveyMetadataIds'],
            [compress, 'compress']]:
            if var:
                data[varname] = var

        # export responses server-side
        downloadBaseUrl = '{}/surveys/{}/export-responses/'.format(self.qualtrics.baseUrl, self.id)
        res = post_request(url=downloadBaseUrl, payload=data)
        progressId = res.json()['result']['progressId']
        while downloadStatus not in ['complete', 'failed']:
            checkStatusUrl = downloadBaseUrl + progressId
            res = get_request(url=checkStatusUrl)
            if verboseRequests:
                downloadProgress = res.json()['result']['percentComplete']
                logging.info("Download is {0:.2f}% complete".format(downloadProgress))
            downloadStatus = res.json()['result']['status']
        if downloadStatus == 'failed':
            raise Exception('export failed')
        fileId = res.json()['result']['fileId']

        # download file from server
        downloadFileUrl = downloadBaseUrl + fileId + '/file'
        res = get_request(url=downloadFileUrl, stream=True)

        # unzip file
        zipfile.ZipFile(io.BytesIO(res.content)).extractall(self.responseFolder)
        if verboseRequests:
            logging.info("File downloaded and extracted")
        self.responsesFile = "{}/{}.{}".format(self.responseFolder, self.name, fileFormat)
        return self.responsesFile

    def get_responses(self,
                      folderName=None,
                      re_download=False,
                      start_date=None,
                      end_date=None,
                      limit=None,
                      use_labels=None,
                      seen_unanswered_recode=None,
                      multiselect_seen_unanswered_recode=None,
                      include_display_order=None,
                      format_decimal_as_comma=None,
                      time_zone=None,
                      newline_replacement=None,
                      question_ids=None,
                      embedded_data_ids=None,
                      survey_metadata_ids=None,
                      compress=None,
                      skipAPICalls: bool = False):
        try:
            if re_download or (folderName and folderName != self.responseFolder) or not self.responsesFile:
                time.sleep(1)  # have to wait for API server to catch up
                self._export_survey(fileFormat='csv',
                                    folderName=folderName,
                                    start_date=start_date,
                                    end_date=end_date,
                                    limit=limit,
                                    use_labels=use_labels,
                                    seen_unanswered_recode=seen_unanswered_recode,
                                    multiselect_seen_unanswered_recode=multiselect_seen_unanswered_recode,
                                    include_display_order=include_display_order,
                                    format_decimal_as_comma=format_decimal_as_comma,
                                    time_zone=time_zone,
                                    newline_replacement=newline_replacement,
                                    question_ids=question_ids,
                                    embedded_data_ids=embedded_data_ids,
                                    survey_metadata_ids=survey_metadata_ids,
                                    compress=compress)
                self.responses = None
            if not self.responses:
                self.responses = []
                with open(self.responsesFile) as f:
                    csvReader = csv.DictReader(f)
                    rows = list(csvReader)
                    for row in rows:
                        self.responses.append(
                            Response(data=row, survey=self, qualtrics=self.qualtrics, skipAPICalls=skipAPICalls))
                self.responses.pop(0)  # first two rows are just a repeat of column headers, delete them
                self.responses.pop(0)
                # for response in self.responses:
                #    self._get_questions_for_response(response)
            return self.responses
        except Exception as e:
            logging.error(e)
            return None

    def get_response(self, response_id, re_download=False, skipAPICalls: bool = False):
        if re_download or not self.responses:
            self.get_responses(re_download=re_download, folderName=self.responseFolder, skipAPICalls=skipAPICalls)
        for response in self.responses:
            if response_id == response.id:
                return response
        return None

    def _create_responses_dataframe(self):
        if self.responsesFile:
            try:
                self.responseDataframe = pd.read_csv(self.responsesFile, skiprows=[1, 2])
                return self.responseDataframe
            except Exception as e:
                logging.error(e)
        return None

    def filter_responses_by_text(self, filters={}, existingFilter=None, saveFilter=False, folderName=None,
                                 re_download=False, dataFrame=False):
        """
        Apply multiple text filters to downloaded responses
        :param filters: a dictionary of {'FieldName1': ['Value1', 'Value2'], 'FieldName2': ['Value1']}
        :param existingFilter: Reuse an existing Filter object
        :param saveFilter: Create and return a Filter object from 'filters'
        :param folderName: specify location of results. Results will be re-downloaded regardless. Optional
        :param re_download: Delete self.responses and force re-download of survey results. Optional
        :param dataFrame: Optionally return a pandas dataframe rather than list of Response objects
        :return: [Response, Response, Response, ...](, Filter (Optional))
        """
        if existingFilter:
            filters = existingFilter.filter
        if re_download or folderName or (self.responseDataframe is None):
            self.get_responses(folderName=folderName, re_download=re_download)
            self._create_responses_dataframe()
        # check for exceptions
        if not filters:
            raise Exception("filters dictionary cannot be empty")
        for field in filters.keys():
            if not self.responses[0].data.get(field):
                raise Exception("'{}' is not a valid response field".format(field))
        for field, values in filters.items():
            if not values:
                raise Exception("'{}' values cannot be empty".format(field))
        if dataFrame:
            responses_dataframe = self.responseDataframe
            masks = []
            for field, values in filters.items():
                masks.append(responses_dataframe[field].isin(values))
            for mask in masks:
                responses_dataframe = responses_dataframe.loc[mask]
            if saveFilter:
                saved_filter = Filter(filters)
                return responses_dataframe, saved_filter
            return responses_dataframe
        else:
            filtered_responses = []
            for response in self.responses:
                passes = True
                for column, values in filters.items():
                    if response.data[column] not in values:
                        passes = False
                        break
                if passes:
                    filtered_responses.append(response)
            return filtered_responses

    def filter_responses_by_date(self, filters: dict = None, existingFilter=None, saveFilter=False, folderName=None,
                                 re_download=False, dataFrame=False):
        """
        Apply multiple date filters to downloaded responses
        :param filters: a dictionary of {'FieldName1': ['Date1', 'before'], 'FieldName2': ['Date2', 'after']}.
        Dates must be in '%Y-%m-%d %H:%M:%S' format
        :param existingFilter: Reuse an existing Filter object
        :param saveFilter: Create and return a Filter object from 'filters'
        :param folderName: specify location of results. Results will be re-downloaded regardless. Optional
        :param re_download: Delete self.responses and force re-download of survey results. Optional
        :param dataFrame: Optionally return a pandas dataframe rather than list of Response objects
        :return: [Response, Response, Response, ...](, Filter (Optional))
        """
        if existingFilter:
            filters = existingFilter.filter
        if re_download or folderName or (self.responseDataframe is None):
            self.get_responses(folderName=folderName, re_download=re_download)
            self._create_responses_dataframe()
        # check for exceptions
        if not filters:
            raise Exception("filters dictionary cannot be empty")
        for field in filters.keys():
            if not self.responses[0].data.get(field):
                raise Exception("'{}' is not a valid response field".format(field))
        for field, values in filters.items():
            if not values or len(values) != 2:
                raise Exception("'{}' value must be ['date', 'before/after']".format(field))
        if dataFrame:
            responses_dataframe = self.responseDataframe
            masks = []
            for field, values in filters.items():
                if not str(values[1]).startswith('be') and not str(values[1]).startswith('a'):
                    raise Exception("'{}' value must be ['date', 'before/after']".format(field))
                if str(values[1]).startswith('b'):  # before
                    masks.append(responses_dataframe[field] < values[0])
                if str(values[1]).startswith('a'):  # after
                    masks.append(responses_dataframe[field] > values[0])
            for mask in masks:
                responses_dataframe = responses_dataframe.loc[mask]
            if saveFilter:
                saved_filter = Filter(filters)
                return responses_dataframe, saved_filter
            return responses_dataframe
        else:
            filtered_responses = []
            for response in self.responses:
                passes = True
                for column, values in filters.items():
                    if not _compare_timestamps(stamp1=response.data[column], stamp2=values[0], beforeAfter=values[1]):
                        passes = False
                        break
                if passes:
                    filtered_responses.append(response)
            return filtered_responses

    def filter_responses_by_answer_to_question(self, question_or_choice_id: str, answer_ids: list = []):
        """
        Alias for filter_responses_by_text
        :param question_or_choice_id: What question are we searching for
        :param answer_ids: What answers to the question are we searching for
        :return: [Response, Response, Response, ...]
        """
        filters = {
            question_or_choice_id: answer_ids
        }
        return self.filter_responses_by_text(filters=filters)

    def get_questions(self, forceUpdate: bool = False):
        if forceUpdate or not self.questions:
            time.sleep(1)  # have to wait for API server to catch up
            questions = []
            res = get_request(
                url='{baseUrl}/survey-definitions/{id}/questions'.format(baseUrl=self.qualtrics.baseUrl, id=self.id))
            if res:
                for question in res.json()['result']['elements']:
                    questions.append(Question(data=question, qualtrics=self.qualtrics))
                self.questions = questions
        return self.questions

    def get_question(self, question_id: str = None, question_text: str = None, forceUpdate: bool = False,
                     skipAPICalls: bool = False):
        if not question_id and not question_text:
            return None
        questions = self.get_questions(forceUpdate=forceUpdate)
        if questions:
            for question in questions:
                if question_id and question_id == question.id:
                    return question
                if question_text and question_text == question.text:
                    return question
        return None

    """
    def create_question(self, 
                        blockId: list = None,
                        choiceOrder: list = None,
                        choices: [Choice] = None,
                        configuration: dict = None,
                        dataExportTag: str = None,
                        language: list = None,
                        questionDescription: str = None,
                        questionText: str = None,
                        questionType: str = None,
                        recodeValues: dict = None,
                        selector: str = None,
                        validation: dict = None,
                        returnNewQuestion: bool = True, 
                        skipAPICalls: bool = False):
        pass
    """

    def _get_questions_for_response(self, response):
        # TODO: Determine how to match seemingly-unrelated response choice ID and question ID, to pass Question
        #  object to Response object
        for question_id, answer_id in response.answers.items():
            for question in self.questions:
                if question_id == question.id:
                    response.questions.append(question)
                    # print(question.data)

    def copy(self, new_name: str = None, new_owner: User = None, new_owner_id: str = None, activateNow: bool = True, returnNewSurvey: bool = True,
             skipAPICalls: bool = False):
        if new_owner:
            new_owner_id = new_owner.id
        elif new_owner_id:
            pass
        else:  # just copy survey under same user
            if not self.owner or not isinstance(self.owner, User):  # self.owner = None or id rather than User object
                new_self_owner = self.qualtrics.get_user(user_id=self.owner)  # try to get User and store as self.owner
                if new_self_owner:
                    self.owner = new_self_owner
                    new_owner_id = self.owner.id
                else:  # if error (401 Unauth), just use the self.owner, which should be an id
                    new_owner_id = self.owner
            else:  # self.owner is User object
                new_owner_id = self.owner.id
        headers = {'Content-Type': 'application/json',
                   'X-API-TOKEN': self.qualtrics.token,
                   'X-COPY-SOURCE': self.id,
                   'X-COPY-DESTINATION-OWNER': new_owner_id
                   }
        data = {}
        if new_name:
            data = {"projectName": new_name}
        res = post_request(url='{}/surveys'.format(self.qualtrics.baseUrl), request_header=headers, payload=data)
        if res:
            new_survey_id = res.json()['result']['id']
            self.qualtrics.get_surveys(forceUpdate=True, skipAPICalls=skipAPICalls)
            if returnNewSurvey:
                retry_limit = 3
                while retry_limit > 0:
                    new_survey = self.qualtrics.get_survey(survey_id=new_survey_id, forceUpdate=True, skipAPICalls=skipAPICalls)
                    if new_survey:
                        if activateNow:
                            new_survey = new_survey.update(isActive=True, skipAPICalls=skipAPICalls)
                        return new_survey
                    retry_limit -= 1
                return new_survey
            return True
        if returnNewSurvey:
            return None
        return False

    def update(self,
               name: str = None,
               isActive: bool = None,
               expiration: str = None,
               owner: User = None,
               returnNewSurvey: bool = True,
               skipAPICalls: bool = False):
        data = {}
        for var, varname in [
            [name, 'name'],
            [expiration, 'expiration'],
        ]:
            if var:
                data[varname] = var
        if isActive is not None:
            data['isActive'] = isActive
        if owner and owner.id:
            data['ownerId'] = owner.id
        res = put_request('{baseUrl}/surveys/{s_id}'.format(baseUrl=self.qualtrics.baseUrl, s_id=self.id),
                          payload=data)
        if res:
            self.qualtrics.get_surveys(forceUpdate=True, skipAPICalls=skipAPICalls)
            if returnNewSurvey:
                return self.qualtrics.get_survey(survey_id=self.id, skipAPICalls=skipAPICalls)
            return True
        if returnNewSurvey:
            return None
        return False

    def delete(self, skipAPICalls: bool = False):
        res = delete_request(url=
                             '{baseUrl}/survey-definitions/{s_id}'.format(baseUrl=self.qualtrics.baseUrl, s_id=self.id))
        if res:
            self.qualtrics.get_surveys(forceUpdate=True, skipAPICalls=skipAPICalls)
            return True
        return False

    def share(self, recipient: User, permissions: Permission, returnSharedUser: bool = True,
              skipAPICalls: bool = False):
        data = {'recipientId': recipient.id,
                'permissions': permissions.data}
        res = post_request(
            url='{baseUrl}/surveys/{s_id}/permissions/collaborations'.format(baseUrl=self.qualtrics.baseUrl,
                                                                             s_id=self.id), payload=data)
        if res:
            self.qualtrics.get_surveys(forceUpdate=True, skipAPICalls=skipAPICalls)
            if returnSharedUser:
                logging.warning("Use the new User for future API calls on this survey")
                return recipient
            return True
        if returnSharedUser:
            return None
        return False

    def get_quotas(self, forceUpdate: bool = False, skipAPICalls: bool = False):
        if forceUpdate or not self.quotas:
            time.sleep(1)  # have to wait for API server to catch up
            res = get_request(url='{baseUrl}/surveys/{id}/quotas'.format(baseUrl=self.qualtrics.baseUrl, id=self.id))
            if res:
                quotas = []
                for quota in res.json()['result']['elements']:
                    quotas.append(Quota(quota))
                self.quotas = quotas
        return self.quotas

    def get_quota(self, quota_id=None, quota_name=None, forceUpdate: bool = False, skipAPICalls: bool = False):
        if not quota_id and not quota_name:
            return None
        quotas = self.get_quotas(forceUpdate=forceUpdate, skipAPICalls=skipAPICalls)
        if quotas:
            for quota in quotas:
                if quota_id and quota_id == quota.id:
                    return quota
                if quota_name and quota_name == quota.name:
                    return quota
        return None

    def get_flow(self, forceUpdate: bool = False, skipAPICalls: bool = False):
        if forceUpdate or not self.flow:
            time.sleep(1)  # have to wait for API server to catch up
            res = get_request(
                '{baseUrl}/survey-definitions/{s_id}/flow'.format(baseUrl=self.qualtrics.baseUrl, s_id=self.id))
            if res:
                self.flow = Flow(data=res.json()['result'], survey=self, qualtrics=self.qualtrics,
                                 skipAPICalls=skipAPICalls)
        return self.flow


class Quota:
    def __init__(self, data):
        self.data = data
        self.id = data.get('id')
        self.name = data.get('name')
        self.count = data.get('count')
        self.quota = data.get('quota')
        self.logicType = data.get('logicType')


class Filter:
    def __init__(self, filter=None, skipAPICalls: bool = False):
        self.filter = filter


class Response:
    def __init__(self, data, survey: Survey, qualtrics: Qualtrics, skipAPICalls: bool = False):
        self.data = data
        self.survey = survey
        self.qualtrics = qualtrics
        self.startDate = data.get('StartDate')
        self.endDate = data.get('EndDate')
        self.status = data.get('Status')
        self.ipAddress = data.get('IPAddress')
        self.progress = data.get('Progress')
        self.duration = data.get('Duration (in seconds)')
        self.finished = data.get('Finished')
        self.recordedDate = data.get('RecordedDate')
        self.id = data.get('ResponseId')
        responderData = {
            'FirstName': data.get('RecipientFirstName'),
            'LastName': data.get('RecipientLastName'),
            'Email': data.get('RecipientEmail'),
        }
        self.responder = Responder(responderData)
        self.externalReference = data.get('ExternalReference')
        self.lat = data.get('LocationLatitude')
        self.long = data.get('LocationLongitude')
        self.distributionChannel = data.get('DistributionChannel')
        self.userLang = data.get('UserLanguage')
        self.questions = []
        self.answers = {}
        for k, v in self.data.items():
            if k.startswith('Q'):
                self.answers[k] = v

    def delete(self, decrementQuotas: str = "true", skipAPICalls: bool = False):
        res = delete_request(
            url='{baseUrl}/surveys/{s_id}/responses/{r_id}?decrementQuotas={quota}'.format(
                baseUrl=self.qualtrics.baseUrl,
                s_id=self.survey.id,
                r_id=self.id,
                quota=decrementQuotas))
        if res:
            self.survey.get_responses(re_download=True)
            return True
        return False

    def update(self,
               data: dict,
               resetRecordedDate: bool = True,
               returnNewResponse: bool = True,
               skipAPICalls: bool = False):
        payload = {'embeddedData': data,
                   'resetRecordedDate': resetRecordedDate
                   }
        res = put_request('{baseUrl}/responses/{r_id}'.format(baseUrl=self.qualtrics.baseUrl, r_id=self.id),
                          payload=payload)
        if res:
            self.survey.get_responses(re_download=True, skipAPICalls=skipAPICalls)
            if returnNewResponse:
                return self.survey.get_response(response_id=self.id, re_download=False)
            return True
        if returnNewResponse:
            return None
        return False


class Question:
    def __init__(self, data, survey: Survey, qualtrics: Qualtrics, response: Response = None,
                 skipAPICalls: bool = False):
        self.data = data
        self.survey = survey
        self.qualtrics = qualtrics
        self.response = response
        self.id = data.get('QuestionID')
        self.text = data.get('QuestionDescription')
        self.html = data.get('QuestionText')
        self.questionType = data.get('QuestionType')
        self.config = data.get('Configuration')
        self.choices = []
        if self.questionType == 'MC':
            for choiceNumber in data.get('Choices'):
                self.choices.append(Choice(data.get('Choices')[choiceNumber], choiceNumber))
            self.choiceOrder = data.get('ChoiceOrder')
        self.validation = data.get('Validation')
        self.language = data.get('Language')
        self.nextChoiceId = data.get('NextChoiceId')
        self.nextAnswerId = data.get('NextAnswerId')
        self.dataVisibility = data.get('DataVisibility')
        self.defaultChoices = data.get('DefaultChoices')
        self.gradingData = data.get('GradingData')
        self.choiceTextPosition = data.get('ChoiceTextPosition')

    """
    def update(self, 
               choiceOrder: list = None,
               choices: [Choice] = None,
               configuration: dict = None,
               dataExportTag: str = None,
               language: list = None,
               questionDescription: str = None,
               questionText: str = None,
               questionType: str = None,
               recodeValues: dict = None,
               selector: str = None,
               validation: dict = None,
               returnNewQuestion: bool = True, 
               skipAPICalls: bool = False):
        pass
    """

    def delete(self, skipAPICalls: bool = False):
        res = delete_request(url=
        '{baseUrl}/survey-definitions/{s_id}/questions/{q_id}'.format(
            baseUrl=self.qualtrics.baseUrl, s_id=self.survey.id, q_id=self.id))
        if res:
            self.survey.get_questions(forceUpdate=True)
            return True
        return False


class Flow:
    def __init__(self, data, survey: Survey, qualtrics: Qualtrics, skipAPICalls: bool = False):
        self.data = data
        self.survey = survey
        self.qualtrics = qualtrics
        self.flowId = data.get('FlowID')
        self.id = data.get('id')
        self.properties = data.get('Properties')
        self.type = data.get('Type')
        if data.get('Flow'):
            self.flows = [Flow(data=item, survey=survey, qualtrics=qualtrics) for item in data.get('Flow')]

    def update(self,
               new_flow_ID: str = None,
               new_type: str = None,
               returnNewFlow: bool = True,
               skipAPICalls: bool = False):
        data = {}
        for var, varname in [
            [new_flow_ID, 'FlowID'],
            [new_type, 'Type']
        ]:
            if var:
                data[varname] = var
        res = put_request(
            '{baseUrl}/survey-definitions/{s_id}/flow/{f_id}'.format(baseUrl=self.qualtrics.baseUrl, s_id=self.surveyid,
                                                                     f_id=self.flowId),
            payload=data)
        if res:
            self.survey.get_flow(forceUpdate=True, skipAPICalls=skipAPICalls)
            if returnNewFlow:
                return self.survey.get_flow(forceUpdate=False, skipAPICalls=skipAPICalls)
            return True
        if returnNewFlow:
            return None
        return False


class Image:
    def __init__(self, data, skipAPICalls: bool = False):
        self.data = data
        if self.data:
            self.name = data.get('Display')
            self.id = data.get('ImageLocation')


class Responder:
    def __init__(self, data, skipAPICalls: bool = False):
        self.data = data
        self.firstName = data.get('FirstName')
        self.lastName = data.get('LastName')
        self.email = data.get('Email')
