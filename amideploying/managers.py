import time
from boto.exception import BotoServerError

import boto.ec2.autoscale
from boto.ec2.autoscale import AutoScalingGroup
from boto.ec2.autoscale import LaunchConfiguration
import boto.ec2.elb

key = "dev-titan"
sg = "sg-6c02f606"
elb = "titan-collector-preview"

profile_name = "preview"

lc_prefix = "titan-lc-"
ag_prefix = "titan-asg-"

region = "us-east-1"
availability_zones = ["us-east-1a"]


def wait_for_status(instances_to_watch, state):
    """Waits for all of the instances to reach the specified state"""
    instance_ids = [instance.id for instance in instances_to_watch]
    print "Waiting for state %s, instances %s" % (state, instance_ids)

    maximum = 60 * 5
    elapsed = 0
    while True:
        assert elapsed < maximum

        for instance in instances_to_watch:
            instance.update()
        if all([
            i.state == state or i.state == "terminated"
            for i in instances_to_watch
        ]):
            break
        print '(%ds) Waiting for state %s...' % (elapsed, state)
        print [
            instance.state
            for instance in instances_to_watch
        ]
        elapsed += 5
        time.sleep(5)


class DeployManager(object):
    def __init__(self, profile, role, config, ami):
        self.profile = profile
        self.role = role
        self.ami = ami
        self.ec2 = boto.ec2.connect_to_region(region, profile_name=profile)
        self.elb = boto.ec2.elb.ELBConnection(profile_name=profile)
        self.autoscale = boto.ec2.autoscale.connect_to_region(region, profile_name=profile)

    def launch_asg(self, ami):
        launch_configuration = LaunchConfiguration(name=lc_prefix + ami, image_id=ami, key_name=key,
                                                   security_groups=[sg],
                                                   instance_type="c3.large")
        self.autoscale.create_launch_configuration(launch_configuration)

        ag = AutoScalingGroup(group_name=ag_prefix + ami, load_balancers=[elb], availability_zones=availability_zones,
                              launch_config=launch_configuration, min_size=2, max_size=4, connection=self.autoscale)
        self.autoscale.create_auto_scaling_group(ag)

        return ag

    def get_asg(self):
        return self.get_asg_by_name(ag_prefix + self.ami)

    def get_asg_by_name(self, name):
        groups = self.autoscale.get_all_groups(names=[name])
        if groups:
            return groups[0]

        return None

    def get_asg_instances(self, group):
        refreshed_group = group
        while True:
            if refreshed_group.instances is not None and len(refreshed_group.instances) > 0:
                break

            refreshed_group = self.get_asg_by_name(group.name)
            time.sleep(2)

        instance_ids = [i.instance_id for i in refreshed_group.instances]
        instances = self.ec2.get_only_instances(instance_ids)
        return instances

    def wait_for_elb_health(self, instances):
        """Waits for all of the instances to be reported as healthy by the ELB"""

        instance_ids = [
            instance.id
            for instance in instances
        ]

        timeout = time.time() + 60 * 10
        elapsed = 0
        while True:
            assert time.time() < timeout
            try:
                health_statuses = self.elb.describe_instance_health(elb, instances=instance_ids)

                if all([
                    status.state == "InService"
                    for status in health_statuses
                ]):
                    break

                print '(%ds) Waiting for instances to be in service on ELB...' % elapsed
                print [
                    status.state
                    for status in health_statuses
                ]
            except BotoServerError:
                print '(%ds) Waiting for instances to be attached to ELB' % elapsed

            elapsed += 5
            time.sleep(5)

    def wait_for_group_to_be_quiet(self, autoscaling_group):
        """Deletes ASG once it has no activities"""

        maximum_wait = 60 * 1
        elapsed = 0
        while True:
            if all([
                activity.progress == '100'
                for activity in autoscaling_group.get_activities()
            ]):
                break

            print "(%ds) ASG has activities with progress %s" % (elapsed, [
                activity.progress
                for activity in autoscaling_group.get_activities()
            ])

            assert elapsed < maximum_wait

            elapsed += 5
            time.sleep(5)
            autoscaling_group = self.get_asg_by_name(autoscaling_group.name)

    def delete_launch_configuration_for_ami(self, ami):
        self.autoscale.delete_launch_configuration(lc_prefix + ami)

    def delete_autoscaling_for_ami(self, ami):
        self.autoscale.delete_auto_scaling_group(ag_prefix + ami)

    def start_ag(self):
        created_ag = self.launch_asg(self.ami)
        print 'Waiting for ASG to be initialized'
        time.sleep(1)

        instances = self.get_asg_instances(created_ag)

        print instances

        wait_for_status(instances, "running")

        print 'Instances running'

        self.wait_for_elb_health(instances)

        print 'Instances attached to ELB'

    def shutdown_other_ags(self):
        keep_ami = self.ami
        groups_to_shut_down = [
            g
            for g in self.autoscale.get_all_groups()
            if g.name != (ag_prefix + keep_ami) and g.name.startswith(ag_prefix)
        ]

        for g in self.autoscale.get_all_groups():
            print g.name

        print "Will shut down %s" % groups_to_shut_down

        for g in groups_to_shut_down:
            ami = g.name[len(ag_prefix):]
            print ami
            self.shutdown_ag_by_ami()

    def shutdown_ag_by_ami(self):
        created_ag = self.get_asg()
        instances = self.get_asg_instances(created_ag)

        print 'Shutting down instances'
        created_ag.shutdown_instances()
        wait_for_status(instances, "terminated")

        print 'Deleting autoscaling group'
        self.wait_for_group_to_be_quiet(created_ag)
        self.delete_autoscaling_for_ami(self.ami)

        print 'Deleting launch configuration'
        self.delete_launch_configuration_for_ami(self.ami)