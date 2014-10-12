# boondoggle

Boondoggle is a little tool meant to simplify deployment of Cloudformation stacks.

## Usage

Given a CloudFormation template residing on S3 that takes two parameters `HttpImage` (an AMI ID) and `DesiredHostCount` (say, the desired count for an Autoscaling Group) deploy with:

```bash
$ boondoggle ensure my-stack --url s3://cf-bucket/my-stack.cf HttpImage:ami-123abc DesiredHostCount:6
```

_If your cloudformation file is local, use `--file` instead of `--url`._

The `ensure` subcommand will create the stack if no such stack currently exists, or update it with the specified template on S3 and parameters if it already exists.

Or cancel an in-progress update to a stack:

```bash
$ boondoggle cancel-update my-stack
```

Or just look up the status of a stack:

```bash
$ boondoggle status my-stack
```

All these commands are _blocking_, so the operation will be allowed to complete before `boondoggle` exits.


```
Options:
  -p --profile=<profile>    Use the specified profile in your .boto
  -r --region=<region>      Use the specified region [default: us-east-1]
  -h --help                 Show this screen.
  -v --version              Show version.
```

## Why not use the AWS CLI?

The AWS CLI provides methods to create and update Cloudformation stacks, but the CLI uses separate commands for creating and updating a stack, and the syntax for stack parameters is rather torturous.

Boondoggle also blocks until the stack update is complete, making it a better fit for CI and deployment.
