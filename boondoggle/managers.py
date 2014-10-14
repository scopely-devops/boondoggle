# Copyright 2014 Scopely, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import time
from os.path import expanduser

import boto.cloudformation as cf
from boto.exception import BotoServerError


class DeployManager(object):
    def __init__(self, region, profile):
        self.region = region
        self.cf = cf.connect_to_region(self.region, profile_name=profile)

    def get_outputs(self, stack):
        """Get the outputs of another stack."""
        try:
            stack = self.cf.describe_stacks(stack_name_or_id=stack)[0]
            return [(output.key, output.value) for output in stack.outputs]
        except BotoServerError as ex:
            print("Something went wrong getting the outputs from this stack.")
            print(ex.body)
            exit(1)

    def ensure(self, name, parameters, url=None, path=None, outputs_from=None):
        # First we check if the stack exists
        status = self.status(name)

        if outputs_from:
            parameters += self.get_outputs(outputs_from)

        args = {'stack_name': name,
                'parameters': parameters}
        if path:
            with open(expanduser(path), 'r') as f:
                args['template_body'] = f.read()
        else:
            args['template_url'] = url

        try:
            if status is None:
                self.cf.create_stack(**args)
            else:
                self.cf.update_stack(**args)
        except BotoServerError, ex:
            if ex.status == 403:
                print("Forbidden! Provided credentials "
                      "cannot create the stack")
                print(ex.body)
                exit(1)
            elif ex.status == 400:
                print("Could not create stack")
                print(ex.body)
                exit(1)
            else:
                raise

        self.wait_for_completion(name)
        outputs = self.get_outputs(name)
        if outputs:
            print("\nOutputs:\n")
            for k, v in outputs:
                print("    {}: {}".format(k, v))
            print('')

    def cancel_update(self, name):
        self.cf.cancel_update_stack(stack_name_or_id=name)
        self.wait_for_completion(name)

    def status(self, name):
        try:
            events = self.cf.describe_stack_events(stack_name_or_id=name)
            if events is not None:
                return events[0]
            else:
                return None
        except BotoServerError, ex:
            if ex.status == 400:
                return None
            if ex.status == 403:
                print("Forbidden! Cannot check status "
                      "with provided credentials")
                exit(1)
            else:
                raise

    def wait_for_completion(self, name):
        good_completed_status = ['CREATE_COMPLETE',
                                 'UPDATE_COMPLETE',
                                 'DELETE_COMPLETE']

        bad_status = ['ROLLBACK_IN_PROGRESS', 'UPDATE_ROLLBACK_IN_PROGRESS',
                      'UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS']

        bad_completed_status = ['CREATE_FAILED', 'ROLLBACK_FAILED',
                                'ROLLBACK_COMPLETE', 'DELETE_FAILED',
                                'DELETE_COMPLETE', 'UPDATE_ROLLBACK_FAILED',
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

            if (last_resource == status_info.physical_resource_id
                    and last_status == status_info.resource_status):
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
                print("({2}s) Stack {0} in intermediate failure "
                      "status {1}, waiting for a final status"
                      .format(name, status, elapsed))
                continue

            if status in bad_completed_status:
                print("({2}s) Stack {0} in status {1}; "
                      "failed to apply template"
                      .format(name, status, elapsed))
                return False

            if status in good_completed_status:
                print("({2}s) Stack {0} in final status {1}; "
                      "succeeded in applying template"
                      .format(name, status, elapsed))
                return True

            print("({2}s) Stack {0} in intermediate status {1}, "
                  "waiting for a final status"
                  .format(name, status, elapsed))
            time.sleep(interval)
            elapsed += interval
