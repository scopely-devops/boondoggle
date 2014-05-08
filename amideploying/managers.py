import time

import boto.cloudformation
from boto.cloudformation.stack import Stack


class DeployManager(object):
    def __init__(self, region):
        self.region = region
        self.cloudformation = boto.cloudformation.connect_to_region(self.region)

    def ensure(self, name, url, parameters):
        # First we check if the stack exists
        description = self.cloudformation.describe_stacks(name)
        if description is None:
            self.cloudformation.create_stack(stack_name=name, template_url=url, parameters=parameters)
        else:
            self.cloudformation.update_stack(stack_name=name, template_url=url, parameters=parameters)

        self.wait_for_completion(name)

    def cancel_update(self, name):
        self.cloudformation.cancel_update_stack(stack_name_or_id=name)
        self.wait_for_completion(name)

    def status(self, name):
        return self.cloudformation.describe_stack_events(stack_name_or_id=name)[0]

    def wait_for_completion(self, name):
        good_completed_status = ['CREATE_COMPLETE', 'UPDATE_COMPLETE', 'DELETE_COMPLETE']

        bad_status = ['ROLLBACK_IN_PROGRESS', 'UPDATE_ROLLBACK_IN_PROGRESS',
                      'UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS']

        bad_completed_status = ['CREATE_FAILED', 'ROLLBACK_FAILED', 'ROLLBACK_COMPLETE',
                                'DELETE_FAILED', 'DELETE_COMPLETE',
                                'UPDATE_ROLLBACK_FAILED',
                                'UPDATE_ROLLBACK_COMPLETE']

        timeout = time.time() + 60 * 10
        interval = 5
        elapsed = 0

        while True:
            assert time.time() < timeout
            status = self.status(name).resource_status
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