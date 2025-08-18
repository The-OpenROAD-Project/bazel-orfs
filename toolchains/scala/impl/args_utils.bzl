"""
This module provides utility functions for working with argument specifications in Scala.
"""

def get_action_type(args_list, action_type):
    """Returns the corresponding entry in ArgsListInfo.by_action.

    Args:
        args_list: (ArgsListInfo) The args list to look through
        action_type: (ActionTypeInfo) The action type to look up.
    Returns:
        The information corresponding to this action type.

    """
    for args in args_list.by_action:
        if args.action == action_type:
            return args

    return struct(action = action_type, args = tuple(), files = depset([]))
