import argparse
import json
import os
import sys
import tempfile
import time
import zipfile
from github import Github, BadCredentialsException, UnknownObjectException
from socket import error as SocketError


class GitHubExport:
    """
    Python project to export a complete GitHub project, fetching all
    the milestones, issues, pull requests and comments.
    """
    per_page = 100
    retrieve_temp = True
    state = 'all'

    def print_json(self):
        """
        Will shows on console all the GutHub Repository information

        :return: None
        """
        print(
            json.dumps(self.get_milestones(), indent=4, sort_keys=True)
        )

    def create_zipfile(self):
        """
        Creates a Zip file on the current directory that contains
        the json exported data

        :return: None
        """
        filename = 'GitHubExport-{}'.format(time.strftime('%Y%m%d-%H%M%S'))
        path_file = os.path.join(tempfile.gettempdir(),
                                 '{}.json'.format(filename))

        with open(path_file, 'w') as outfile:
            json.dump(self.get_milestones(), outfile)

        zf = zipfile.ZipFile('{}.zip'.format(filename), 'w')
        zf.write(path_file, '{}.json'.format(filename))
        zf.close()

    def get_milestones(self):
        """
        Will return a dictionary with all the milestones with issues
        and pull requests

        :return: dictionary With all the milestones including
        issues and pull requests without a milestone associated
        """
        self._check_rate_limit()
        milestones_repo = self.repo.get_milestones(state=self.state)
        milestones = self._fetch_all(milestones_repo)
        milestones.append('none')

        return {
            'milestones': self._build_raw_milestones(milestones)
        }

    def get_issues_and_pulls(self, milestone):
        """
        Fetch all the issues and pull requests of the passed milestone

        :param milestone: MilestoneObject or String of the related milestone
        :return: [list, list] Will return all the issues and pull requests
        """
        self._check_rate_limit()
        issues = self.repo.get_issues(milestone=milestone, state=self.state)
        all_issues = self._fetch_all(issues)
        issues_list = []
        pulls_list = []
        for issue in all_issues:
            if not issue.pull_request:
                issues_list.append(issue)
            else:
                pulls_list.append(issue)

        return issues_list, pulls_list

    def get_comments(self, issue):
        """
        Fetch all the comments of the passed issue

        :param issue: IssueObject Of the related issue
        :return: list Will return a list of comments
        """
        self._check_rate_limit()
        comments = issue.get_comments()
        return self._fetch_all(comments, True)

    def _get_temp_dir(self):
        return os.path.join(tempfile.gettempdir(), self.organization,
                            self.repository)

    def _build_raw_issues(self, issues):
        """
        Will return all the issues with the comments and as
        a Dictionary

        :param issues: List of IssueObject to be updated with
        comments
        :return: list With all the issues as a Dictionary
        """
        raw_issues = []

        for issue in issues:
            stored_object = self._get_temp_file(issue.id, 'issue')
            if stored_object:
                raw_issues.append(stored_object)
                continue

            raw_issue = issue.raw_data
            raw_issue.update({
                'comments': self.get_comments(issue)
            })
            raw_issues.append(raw_issue)
            self._set_temp_file(issue.id, 'issue', raw_issue)

        return raw_issues

    def _build_raw_milestones(self, milestones):
        """
        Will return all the milestones with the issues and pull requests as
        a Dictionary

        :param milestones: List of MilestoneObject to be updated with
        issues and pull requests
        :return: list With all the milestones as a Dictionary
        """
        raw_milestones = []

        for i, milestone in enumerate(milestones):
            milestone_id = milestone.id if hasattr(milestone, 'id') else None
            stored_object = self._get_temp_file(milestone_id, 'milestone')
            if stored_object:
                raw_milestones.append(stored_object)
                continue

            self._display_percentage((i+1)*100/len(milestones))
            issues, pulls = self.get_issues_and_pulls(milestone)
            if milestone != 'none':
                raw_milestone = milestone.raw_data
            else:
                raw_milestone = {
                    'id': milestone_id
                }
            raw_milestone.update({
                'issues': self._build_raw_issues(issues),
                'pulls': self._build_raw_issues(pulls)
            })
            raw_milestones.append(raw_milestone)
            self._set_temp_file(milestone_id, 'milestone', raw_milestone)

        return raw_milestones

    def _get_temp_file(self, obj_id, obj_type):
        if self.retrieve_temp:
            file_name = os.path.join(self._get_temp_dir(), '{}-{}.json'.format(obj_type, obj_id))
            if os.path.isfile(file_name):
                with open(file_name) as json_file:
                    return json.load(json_file)
            else:
                return None

    def _set_temp_file(self, obj_id, obj_type, data):
        if self.retrieve_temp:
            file_name = os.path.join(self._get_temp_dir(), '{}-{}.json'.format(obj_type, obj_id))
            if not os.path.exists(self._get_temp_dir()):
                os.makedirs(self._get_temp_dir())
            with open(file_name, 'w') as outfile:
                json.dump(data, outfile)

    def _fetch_all(self, obj, raw_data=False):
        """
        Fetch all the pages of the GitHub repository

        :param obj: PaginatedList to be fetched
        :param raw_data: Creates an object from raw_data previously obtained
        :return: list Of GitHubObjects or Objects with data
        """
        data = []
        i = 0
        last_page = False

        while not last_page:
            j = 0
            self._check_rate_limit()
            try:
                page_data = obj.get_page(i)
            except TypeError:
                last_page = True
            while j < self.per_page and not last_page:
                try:
                    if raw_data:
                        data.append(page_data[j].raw_data)
                    else:
                        data.append(page_data[j])
                except IndexError:
                    last_page = True
                j += 1
            i += 1

        return data

    @staticmethod
    def _display_percentage(progress):
        sys.stdout.write('\r[{}] {}%'.format('#'*(progress/2), progress))
        sys.stdout.flush()

    def _check_rate_limit(self):
        # Prevents that the server gets down by all the consumed data
        remaining, limit = self.gitHub.rate_limiting
        if abs(remaining) < 100:
            time.sleep(60 * 2)

    def clean_temp(self):
        if os.path.exists(self._get_temp_dir()):
            files = [f for f in os.listdir(self._get_temp_dir()) if f.endswith('.json')]
            for f in files:
                os.remove(f)

    def __init__(self, login_or_token, organization, repository,
                 password=None):
        self.organization = organization
        self.repository = repository
        repo_name = '{}/{}'.format(organization, repository)

        self.gitHub = Github(login_or_token, password, per_page=self.per_page)
        self.repo = self.gitHub.get_repo(repo_name)


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description='GitHubExport will iterate over each milestone and return '
                    'all the issues and pull requests with comments.',
        epilog='The default result will create a zipfile that contains a json '
               'file with the exported repository. If print_json is set the '
               'console will print all the data.'
    )
    parser.add_argument('-u', '--user-token', type=str, required=True,
                        help='GitHub user or API Token')
    parser.add_argument('-p', '--password', type=str, required=False,
                        help='GitHub password (optional)')
    parser.add_argument('-o', '--owner', type=str, required=True,
                        help='Owner of GitHub project')
    parser.add_argument('-r', '--repository', type=str, required=True,
                        help='GitHub repository')
    parser.add_argument('--print_json', action='store_true', default=False,
                        help='Prints JSON result')
    parser.add_argument('--clean_temp', action='store_true', default=False,
                        help='Clear all files on the temporary directory')
    args = parser.parse_args()

    g = GitHubExport(args.user_token, args.owner, args.repository,
                     args.password)

    if args.clean_temp:
        g.clean_temp()
    try:
        if args.print_json:
            g.print_json()
        else:
            g.create_zipfile()
    except BadCredentialsException:
        print('Error: Incorrect credentials')
    except UnknownObjectException:
        print('Error: Incorrect GitHub owner or repository')


if __name__ == '__main__':
    main()
