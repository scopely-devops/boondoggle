import time

import boto.cloudformation
from boto.cloudformation.stack import Stack
from boto.exception import BotoServerError


class DeployManager(object):
    def __init__(self, region, profile):
        self.region = region
        self.cloudformation = boto.cloudformation.connect_to_region(self.region, profile_name=profile)

    def ensure(self, name, url, parameters):
        # First we check if the stack exists
        status = self.status(name)

        try:
            if status is None:
                self.cloudformation.create_stack(stack_name=name, template_url=url, parameters=parameters)
            else:
                self.cloudformation.update_stack(stack_name=name, template_url=url, parameters=parameters)
        except BotoServerError, ex:
            if ex.status == 403:
                print("Forbidden! Provided credentials cannot create the stack")
                print ex.body
                exit(1)
            elif ex.status == 400:
                print("Could not create stack")
                print ex.body
                exit(1)
            else:
                raise

        self.wait_for_completion(name)

    def cancel_update(self, name):
        self.cloudformation.cancel_update_stack(stack_name_or_id=name)
        self.wait_for_completion(name)

    def status(self, name):
        try:
            events = self.cloudformation.describe_stack_events(stack_name_or_id=name)
            if events is not None:
                return events[0]
            else:
                return None
        except BotoServerError, ex:
            if ex.status == 400:
                return None
            if ex.status == 403:
                print("Forbidden! Cannot check status with provided credentials")
                exit(1)
            else:
                raise

    def wait_for_completion(self, name):
        good_completed_status = ['CREATE_COMPLETE', 'UPDATE_COMPLETE', 'DELETE_COMPLETE']

        bad_status = ['ROLLBACK_IN_PROGRESS', 'UPDATE_ROLLBACK_IN_PROGRESS',
                      'UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS']

        bad_completed_status = ['CREATE_FAILED', 'ROLLBACK_FAILED', 'ROLLBACK_COMPLETE',
                                'DELETE_FAILED', 'DELETE_COMPLETE',
                                'UPDATE_ROLLBACK_FAILED',
                                'UPDATE_ROLLBACK_COMPLETE']

        # Give 45 minutes for operation completion
        timeout = time.time() + 60 * 45
        interval = 2
        elapsed = 0

        last_resource = ""
        last_status = ""

        while True:
            assert time.time() < timeout
            status_info = self.status(name)

            if last_resource == status_info.physical_resource_id and last_status == status_info.resource_status:
                time.sleep(1)
                elapsed += 1
                continue

            last_resource = status_info.physical_resource_id
            last_status = status_info.resource_status

            if status_info.logical_resource_id != name:
                print("({2}s) Resource {0} in status {1} ({3})"
                      .format(status_info.logical_resource_id,
                              status_info.resource_status,
                              elapsed,
                              status_info.physical_resource_id))
                time.sleep(interval)
                elapsed += interval
                continue

            status = status_info.resource_status
            if status in bad_status:
                print("({2}s) Stack {0} in intermediate failure status {1}, waiting for a final status"
                      .format(name, status, elapsed))
                continue

            if status in bad_completed_status:
                print("({2}s) Stack {0} in status {1}; failed to apply template"
                      .format(name, status, elapsed))
                return False

            if status in good_completed_status:
                print("({2}s) Stack {0} in final status {1}; succeeded in applying template"
                      .format(name, status, elapsed))
                return True

            print("({2}s) Stack {0} in intermediate status {1}, waiting for a final status"
                  .format(name, status, elapsed))
            time.sleep(interval)
            elapsed += interval