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


def get_latest_amazon_ami():
    """
    Get latest Amazon AMI
    """

    client = boto3.client("ec2", region_name="us-east-1")

    response = client.describe_images(
        Filters=[
            {"Name": "name", "Values": ["amzn2-ami-hvm*"]},
            {"Name": "virtualization-type", "Values": ["hvm"]},
            {"Name": "architecture", "Values": ["x86_64*"]},
            {"Name": "root-device-type", "Values": ["ebs"]},
        ],
        Owners=["amazon"],
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
    # print(args_dict)
    return args_dict


def main():
    """
    Run transformations to create marketplace template
    """

    # Set variables
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

    source_file = "templates/aws-cf-asg.yaml"
    mappings_file = "helpers/marketplace-template/mappings.json"

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
        image_id = get_latest_amazon_ami()

    # Add mappings and replace ami
    with open(mappings_file, "r") as mappings:
        data = update_key(json.load(mappings), "ImageId", image_id)
        template.insert(5, "Mappings", data["Mappings"])

    template["Resources"]["LaunchConfig"]["Properties"]["ImageId"] = {
        "Fn::FindInMap": ["RegionMap", {"Ref": "AWS::Region"}, "ImageId"]
    }

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

    # Add disclaimer and result to file
    with open(args.out, "w+") as tmpl_dest:
        tmpl_dest.write("# This file is auto-generated. Manual changes will be lost.\n")
        tmpl_dest.write(
            "# https://github.com/barracuda-cloudgen-access/aws-templates\n"
        )
        yaml.dump(template, tmpl_dest)


if __name__ == "__main__":
    main()
