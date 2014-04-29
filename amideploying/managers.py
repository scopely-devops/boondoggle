import time
from boto.exception import BotoServerError

import boto.ec2.autoscale
from boto.ec2.autoscale import AutoScalingGroup
from boto.ec2.autoscale import LaunchConfiguration
import boto.ec2.elb


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

        self.region = config['region']
        self.availability_zones = config['availability_zones']
        self.security_groups = config['security_groups']
        self.lc_prefix = config['lc_prefix']
        self.ag_prefix = config['ag_prefix']
        self.key = config['key']
        self.instance_type = config['instance_type']
        self.load_balancers = config['load_balancers']
        self.cluster_minimum_size = config['cluster_minimum_size']
        self.cluster_maximum_size = config['cluster_maximum_size']

        self.ec2 = boto.ec2.connect_to_region(self.region, profile_name=profile)
        self.elb = boto.ec2.elb.ELBConnection(profile_name=profile)
        self.autoscale = boto.ec2.autoscale.connect_to_region(self.region, profile_name=profile)

    def launch_asg(self):
        launch_configuration = LaunchConfiguration(name=self.lc_prefix + self.ami, image_id=self.ami, key_name=self.key,
                                                   security_groups=self.security_groups,
                                                   instance_type=self.instance_type)
        self.autoscale.create_launch_configuration(launch_configuration)

        ag = AutoScalingGroup(group_name=self.ag_prefix + self.ami, load_balancers=self.load_balancers,
                              availability_zones=self.availability_zones,
                              launch_config=launch_configuration, min_size=self.cluster_minimum_size,
                              max_size=self.cluster_maximum_size, connection=self.autoscale)
        self.autoscale.create_auto_scaling_group(ag)

        return ag

    def get_asg(self, ami):
        return self.get_asg_by_name(self.ag_prefix + ami)

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
                # TODO Support health check on all ELBs, not just the first one
                health_statuses = self.elb.describe_instance_health(self.load_balancers[0], instances=instance_ids)

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
        self.autoscale.delete_launch_configuration(self.lc_prefix + ami)

    def delete_autoscaling_for_ami(self, ami):
        self.autoscale.delete_auto_scaling_group(self.ag_prefix + ami)

    def start_ag(self):
        print "Starting autoscaling for role {0} using AMI {1}".format(self.role, self.ami)
        created_ag = self.launch_asg()
        print 'Waiting for ASG to be initialized'
        time.sleep(1)

        instances = self.get_asg_instances(created_ag)

        print instances

        wait_for_status(instances, "running")

        print 'Instances running'

        if len(self.elb) > 0:
            self.wait_for_elb_health(instances)
            print 'Instances attached to ELB'
        else:
            print 'Skipping ELB health check'

    def shutdown_other_ags(self):
        keep_ami = self.ami
        groups_to_shut_down = [
            g
            for g in self.autoscale.get_all_groups()
            if g.name != (self.ag_prefix + keep_ami) and g.name.startswith(self.ag_prefix)
        ]

        for g in self.autoscale.get_all_groups():
            print g.name

        print "Will shut down %s" % groups_to_shut_down

        for g in groups_to_shut_down:
            ami = g.name[len(self.ag_prefix):]
            print ami
            self.shutdown_ag_by_ami(ami)

    def shutdown_ag_by_ami(self, ami):
        created_ag = self.get_asg(ami)
        instances = self.get_asg_instances(created_ag)

        print('Shutting down instances')
        created_ag.shutdown_instances()
        wait_for_status(instances, "terminated")

        print('Deleting autoscaling group')
        self.wait_for_group_to_be_quiet(created_ag)
        self.delete_autoscaling_for_ami(ami)

        print 'Deleting launch configuration'
        self.delete_launch_configuration_for_ami(ami)