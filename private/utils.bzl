"""Pure utility functions for OpenROAD-flow-scripts Bazel rules."""

def file_path(f, short = False):
    """Returns short_path or path depending on the short flag.

    Args:
      f: A File object.
      short: If True, return short_path; otherwise return path.

    Returns:
      The file's short_path or path.
    """
    return f.short_path if short else f.path

def union(*lists):
    """Returns the union of multiple lists, removing duplicates.

    Args:
      *lists: Lists to merge.

    Returns:
      A list with unique elements from all input lists.
    """
    merged_dict = {}
    for list1 in lists:
        dict1 = {key: True for key in list1}
        merged_dict.update(dict1)

    return list(merged_dict.keys())

def commonprefix(*args):
    """
    Return the longest path prefix.

    Return the longest path prefix (taken character-by-character)
    that is a prefix of all paths in `*args`. If `*args` is empty,
    return the empty string ('').

    Args:
      *args: Sequence of strings.
    Returns:
      Longest common prefix of each string in `*args`.
    """
    prefix = ""
    for t in zip(*args):
        for x in t:
            if x != t[0]:
                return prefix
        prefix += t[0]

    return prefix

def commonpath(files):
    """
    Return the longest common sub-path of each file in the sequence `files`.

    Args:
      files: Sequence of files.

    Returns:
      Longest common sub-path of each file in the sequence `files`.
    """
    prefix = commonprefix(*[f.path.elems() for f in files])
    path, _, _ = prefix.rpartition("/")
    return path

def flatten(xs):
    """Flattens a nested list iteratively.

    Args:
        xs: A list that may contain other lists, maximum two levels
    Returns:
        A flattened list.
    """
    result = []
    for x in xs:
        if type(x) == "list":
            for y in x:
                if type(y) == "list":
                    fail("Nested lists are not supported")
                else:
                    result.append(y)
        else:
            result.append(x)
    return result

def set(iterable):
    """Creates a set-like collection from an iterable.

    Args:
        iterable: An iterable containing elements.
    Returns:
        A list with unique elements.
    """
    unique_dict = {}
    for item in iterable:
        unique_dict[item] = True
    return list(unique_dict.keys())
