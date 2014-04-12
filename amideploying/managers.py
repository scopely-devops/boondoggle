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


def launch_asg(ami):
    """Creates ASG for the specified AMI and returns it.

    :param ami:
    """
    autoscale = boto.ec2.autoscale.connect_to_region(region, profile_name=profile_name)

    launch_configuration = LaunchConfiguration(name=lc_prefix + ami, image_id=ami, key_name=key, security_groups=[sg],
                                               instance_type="c3.large")
    autoscale.create_launch_configuration(launch_configuration)

    ag = AutoScalingGroup(group_name=ag_prefix + ami, load_balancers=[elb], availability_zones=['us-east-1a'],
                          launch_config=launch_configuration, min_size=2, max_size=4, connection=autoscale)
    autoscale.create_auto_scaling_group(ag)

    return ag


def get_asg(ami):
    return get_asg_by_name(ag_prefix + ami)


def get_asg_by_name(name):
    autoscale = boto.ec2.autoscale.connect_to_region(region, profile_name=profile_name)
    groups = autoscale.get_all_groups(names=[name])
    if groups:
        return groups[0]

    return None


def get_asg_instances(group):
    ec2 = boto.ec2.connect_to_region(region, profile_name=profile_name)

    refreshed_group = group
    while True:
        if refreshed_group.instances is not None and len(refreshed_group.instances) > 0:
            break

        refreshed_group = get_asg_by_name(group.name)
        time.sleep(2)

    instance_ids = [i.instance_id for i in refreshed_group.instances]
    instances = ec2.get_only_instances(instance_ids)
    return instances


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


def wait_for_elb_health(instances):
    """Waits for all of the instances to be reported as healthy by the ELB"""

    elb_connection = boto.ec2.elb.connect_to_region(region, profile_name=profile_name)

    instance_ids = [
        instance.id
        for instance in instances
    ]

    timeout = time.time() + 60 * 10
    elapsed = 0
    while True:
        assert time.time() < timeout
        try:
            health_statuses = elb_connection.describe_instance_health(elb, instances=instance_ids)

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


def wait_for_group_to_be_quiet(autoscaling_group):
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
        autoscaling_group = get_asg_by_name(autoscaling_group.name)


def delete_launch_configuration_for_ami(ami):
    autoscale = boto.ec2.autoscale.connect_to_region(region, profile_name=profile_name)
    autoscale.delete_launch_configuration(lc_prefix + ami)


def delete_autoscaling_for_ami(ami):
    autoscale = boto.ec2.autoscale.connect_to_region(region, profile_name=profile_name)
    autoscale.delete_auto_scaling_group(ag_prefix + ami)


def start_ag(ami):
    created_ag = launch_asg(ami)
    print 'Waiting for ASG to be initialized'
    time.sleep(1)

    instances = get_asg_instances(created_ag)

    print instances

    wait_for_status(instances, "running")

    print 'Instances running'

    wait_for_elb_health(instances)

    print 'Instances attached to ELB'


def shutdown_other_ags(keep_ami):
    autoscale = boto.ec2.autoscale.connect_to_region(region, profile_name=profile_name)
    groups_to_shut_down = [
        g
        for g in autoscale.get_all_groups()
        if g.name != (ag_prefix + keep_ami) and g.name.startswith(ag_prefix)
    ]

    for g in autoscale.get_all_groups():
        print g.name

    print "Will shut down %s" % groups_to_shut_down

    for g in groups_to_shut_down:
        ami = g.name[len(ag_prefix):]
        print ami
        shutdown_ag_by_ami(ami)


def shutdown_ag_by_ami(ami):
    created_ag = get_asg(ami)
    instances = get_asg_instances(created_ag)

    print 'Shutting down instances'
    created_ag.shutdown_instances()
    wait_for_status(instances, "terminated")

    print 'Deleting autoscaling group'
    wait_for_group_to_be_quiet(created_ag)
    delete_autoscaling_for_ami(ami)

    print 'Deleting launch configuration'
    delete_launch_configuration_for_ami(ami)