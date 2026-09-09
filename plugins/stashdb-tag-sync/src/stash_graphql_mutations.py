"""Raw GraphQL mutations for Stash API operations."""

UPDATE_TAG_MUTATION = """
mutation TagUpdate($input: TagUpdateInput!) {
    tagUpdate(input: $input) {
        id
    }
}
"""
