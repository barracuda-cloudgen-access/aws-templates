#!/usr/bin/env python3
"""
Create marketplace template from aws-cf-asg.yaml
"""

import argparse
import json
from collections import OrderedDict
from operator import itemgetter

import boto3
from ruamel.yaml import YAML


class OrderedDictInsert(OrderedDict):
    """
    Add new class to OrderedDict
    """

    def insert(self, index, key, value):
        """
        Insert key on specified index
        """

        self[key] = value
        for i, k in enumerate(list(self.keys())):
            if i >= index and k != key:
                self.move_to_end(k)


def get_latest_amazon_ami(name, owner, region):
    """
    Get latest Amazon AMI
    """

    client = boto3.client("ec2", region_name=region)

    response = client.describe_images(
        Filters=[
            {"Name": "name", "Values": [name]},
            {"Name": "virtualization-type", "Values": ["hvm"]},
            {"Name": "architecture", "Values": ["x86_64*"]},
            {"Name": "root-device-type", "Values": ["ebs"]},
        ],
        Owners=[owner],
    )

    # Sort on Creation date Desc
    image_details = sorted(
        response["Images"], key=itemgetter("CreationDate"), reverse=True
    )

    return image_details[0]["ImageId"]


def update_key(args_dict, key_to_update, replace_value):
    """
    Searches and replaces text in keys from received dictionary
    """

    for key, value in args_dict.items():
        if isinstance(value, dict):
            args_dict[key] = update_key(value, key_to_update, replace_value)

    if key_to_update in args_dict:
        args_dict[key_to_update] = replace_value

    return args_dict


def insert_if_found_ordered_dict(obj, key, new_item):
    """
    Searches for key and inserts new_item from received obj when found
    """

    id_temp = next((index for index, value in enumerate(obj) if key in value), -1)

    if id_temp >= 0:
        obj.insert(id_temp + 1, *new_item)


def insert_if_found_list(obj, search_key, search_item, new_item):
    """
    Searches for search_parameter on search_key and inserts new_item
    from received obj when found
    """

    for _, key_temp in enumerate(obj):
        for key2_temp in key_temp[search_item]:
            if search_key in key2_temp:
                key_temp[search_item].append(new_item)


def replace_if_found_ordered_dict(obj, key, new_item):
    """
    Searches for key and replaces new_item from received obj when found
    """

    id_temp = next((index for index, value in enumerate(obj) if key in value), -1)

    if id_temp >= 0:
        obj[id_temp + 1] = new_item


def main():
    """
    Run transformations to create marketplace template
    """

    # Set arguments
    parser = argparse.ArgumentParser(description="Create marketplace template")
    parser.add_argument(
        "--out",
        type=str,
        help="Output file",
        default="templates/aws-cf-asg-marketplace.yaml",
    )
    parser.add_argument(
        "--no-creds",
        default=False,
        action="store_true",
        help="Run without requiring AWS credentials",
    )
    args = parser.parse_args()

    # Variables
    source_file = "templates/aws-cf-asg.yaml"
    mappings_file = "helpers/marketplace-template/mappings.json"
    ami = {
        "name": "amazonlinux-2-cga-proxy-base_*",
        "owner": "766535289950",
        "region": "us-east-1",
    }
    cga_config = {
        "cloudwatch": {
            "url": "https://url.access.barracuda.com/config-ec2-cloudwatch-logs",
            "file": "/usr/local/config-ec2-cloudwatch-logs.sh",
        },
        "proxy": {
            "url": "https://url.access.barracuda.com/proxy-linux",
            "file": "/usr/local/proxy-linux.sh",
        },
        "harden": {
            "url": "https://url.access.barracuda.com/harden-linux",
            "file": "/usr/local/harden-linux.sh",
        },
    }

    # Read yaml
    with open(source_file, "r") as tmpl_origin:
        yaml = YAML()
        yaml.explicit_start = True
        yaml.preserve_quotes = True
        yaml.indent(mapping=2, sequence=4, offset=2)
        template = yaml.load(tmpl_origin)

    # Update description
    template["Description"] = template["Description"] + " for AWS Marketplace"

    # Get latest ami
    if args.no_creds:
        image_id = "ami-placeholder"
    else:
        image_id = get_latest_amazon_ami(ami["name"], ami["owner"], ami["region"])

    # Add mappings and replace ami
    with open(mappings_file, "r") as mappings:
        data = update_key(json.load(mappings), "ImageId", image_id)
        template.insert(5, "Mappings", data["Mappings"])

    template["Resources"]["LaunchTemplate"]["Properties"]["LaunchTemplateData"][
        "ImageId"
    ] = {"Fn::FindInMap": ["RegionMap", {"Ref": "AWS::Region"}, "ImageId"]}

    # Remove EC2AMI
    for index, key in enumerate(
        template["Metadata"]["AWS::CloudFormation::Interface"]["ParameterGroups"]
    ):
        for key2 in key["Parameters"]:
            if "EC2AMI" in key2:
                temp_object = [x for x in key["Parameters"] if "EC2AMI" not in x]
                template["Metadata"]["AWS::CloudFormation::Interface"][
                    "ParameterGroups"
                ][index]["Parameters"] = temp_object

    del template["Metadata"]["AWS::CloudFormation::Interface"]["ParameterLabels"][
        "EC2AMI"
    ]

    del template["Parameters"]["EC2AMI"]

    # Add AccessProxyAllowPublicAccess parameter
    insert_if_found_list(
        template["Metadata"]["AWS::CloudFormation::Interface"]["ParameterGroups"],
        "AccessProxyPublicPort",
        "Parameters",
        "AccessProxyAllowPublicAccess",
    )

    insert_if_found_ordered_dict(
        template["Metadata"]["AWS::CloudFormation::Interface"]["ParameterLabels"],
        "AccessProxyPublicPort",
        (
            "AccessProxyAllowPublicAccess",
            {"default": "Allow public access to Access Proxy"},
        ),
    )

    insert_if_found_ordered_dict(
        template["Parameters"],
        "AccessProxyPublicPort",
        (
            "AccessProxyAllowPublicAccess",
            {
                "Description": "(!!!) Please select 'true' to allow external connections (!!!)",
                "Type": "String",
                "Default": "false",
                "AllowedValues": ["true", "false"],
            },
        ),
    )

    template["Conditions"].insert(
        0,
        "AccessProxyAllowPublicAccessTrue",
        {"Fn::Equals": [{"Ref": "AccessProxyAllowPublicAccess"}, True]},
    )

    template["Resources"]["InboundEC2SecGroup"]["Properties"]["SecurityGroupIngress"][
        0
    ]["CidrIp"] = {
        "Fn::If": [
            "AccessProxyAllowPublicAccessTrue",
            "0.0.0.0/0",
            {"Ref": "AWS::NoValue"},
        ]
    }

    # Add AccessProxyGetLatestScripts parameter
    insert_if_found_list(
        template["Metadata"]["AWS::CloudFormation::Interface"]["ParameterGroups"],
        "AccessProxyAllowPublicAccess",
        "Parameters",
        "AccessProxyGetLatestScripts",
    )

    insert_if_found_ordered_dict(
        template["Metadata"]["AWS::CloudFormation::Interface"]["ParameterLabels"],
        "AccessProxyAllowPublicAccess",
        (
            "AccessProxyGetLatestScripts",
            {"default": "Get the latest Access Proxy install scripts"},
        ),
    )

    insert_if_found_ordered_dict(
        template["Parameters"],
        "AccessProxyAllowPublicAccess",
        (
            "AccessProxyGetLatestScripts",
            {
                "Description": "Select 'true' to get the latest install scripts."
                + "When 'false' the scripts included with the AMI will be used.",
                "Type": "String",
                "Default": "false",
                "AllowedValues": ["true", "false"],
            },
        ),
    )

    template["Conditions"].insert(
        0,
        "AccessProxyGetLatestScriptsTrue",
        {"Fn::Equals": [{"Ref": "AccessProxyGetLatestScripts"}, True]},
    )

    replace_if_found_ordered_dict(
        template["Resources"]["LaunchTemplate"]["Properties"]["LaunchTemplateData"][
            "UserData"
        ]["Fn::Base64"]["Fn::Join"][1],
        "# Install CloudWatch Agent",
        {
            "Fn::If": [
                "CloudWatchLogsEnabled",
                {
                    "Fn::If": [
                        "AccessProxyGetLatestScriptsTrue",
                        'curl -sL "{}" | bash -s -- \\'.format(
                            cga_config["cloudwatch"]["url"]
                        ),
                        "{} \\".format(cga_config["cloudwatch"]["file"]),
                    ]
                },
                {"Ref": "AWS::NoValue"},
            ]
        },
    )

    replace_if_found_ordered_dict(
        template["Resources"]["LaunchTemplate"]["Properties"]["LaunchTemplateData"][
            "UserData"
        ]["Fn::Base64"]["Fn::Join"][1],
        "# Install CloudGen Access Proxy",
        {
            "Fn::If": [
                "AccessProxyGetLatestScriptsTrue",
                'curl -sL "{}" | bash -s -- \\'.format(cga_config["proxy"]["url"]),
                "{} \\".format(cga_config["proxy"]["file"]),
            ]
        },
    )

    replace_if_found_ordered_dict(
        template["Resources"]["LaunchTemplate"]["Properties"]["LaunchTemplateData"][
            "UserData"
        ]["Fn::Base64"]["Fn::Join"][1],
        "# Harden instance and reboot",
        {
            "Fn::If": [
                "AccessProxyGetLatestScriptsTrue",
                'curl -sL "{}" | bash -s --'.format(cga_config["harden"]["url"]),
                cga_config["harden"]["file"],
            ]
        },
    )

    # Add disclaimer and result to file
    with open(args.out, "w+") as tmpl_dest:
        tmpl_dest.write("# This file is auto-generated. Manual changes will be lost.\n")
        tmpl_dest.write(
            "# https://github.com/barracuda-cloudgen-access/aws-templates\n"
        )
        yaml.dump(template, tmpl_dest)


if __name__ == "__main__":
    main()
