"""Raw GraphQL mutations for Stash API operations."""

UPDATE_TAG_STASH_IDS_MUTATION = """
mutation UpdateTagStashIDs($input: TagUpdateInput!) {
    tagUpdate(input: $input) {
        id
        stash_ids {
            endpoint
            stash_id
        }
    }
}
"""
