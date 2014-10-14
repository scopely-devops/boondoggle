#!/usr/bin/env python
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

"""A script for managing stacks using Cloudformation templates"""
import click

from boondoggle.managers import DeployManager
from boondoggle import __version__


@click.group()
@click.version_option(__version__, prog_name="Boondoggle")
@click.option('--profile', '-p',
              help="Use the specified profile in your .boto")
@click.option('--region', '-r',
              default='us-east-1',
              help="Use the specified region (defaults to us-east-1)")
@click.pass_context
def cli(context, profile, region):
    context.obj = DeployManager(region=region, profile=profile)


@cli.command()
@click.pass_context
@click.argument('name')
@click.argument('params', nargs=-1)
@click.option('--url',
              help="URL of a cloudformation script.")
@click.option('--file',
              help="Path to a cloudformation file.")
@click.option('--outputs-from',
              help="Use another stack's outputs as inputs to this one.")
def ensure(context, name, params, url, file, outputs_from):
    """Updates the stack with the given name to use
    the specified template. This creates the stack if
    necessary.

    """
    template_parameters = []
    if params:
        for param in params:
            k, v = param.split(':', 1)
            template_parameters.append((k, v))
        context.obj.ensure(name, template_parameters,
                           url=url, path=file,
                           outputs_from=outputs_from)


@cli.command()
@click.argument('name')
@click.pass_context
def cancel_update(context, name):
    """Cancels an in-progress update on the specified stack."""
    context.obj.cancel_update(name)


@cli.command()
@click.argument('name')
@click.pass_context
def status(context, name):
    """Returns the current status of the specified stack."""
    status = context.obj.status(name)
    if not status:
        print("No matching stack")
    else:
        print(status)
