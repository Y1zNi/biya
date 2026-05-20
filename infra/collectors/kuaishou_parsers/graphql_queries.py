"""快手 GraphQL 查询语句."""

COMMENT_LIST_QUERY = """
query commentListQuery($photoId: String, $pcursor: String) {
  visionCommentList(photoId: $photoId, pcursor: $pcursor) {
    commentCount
    commentCountV2
    pcursor
    rootCommentsV2 {
      commentId
      authorId
      authorName
      content
      headurl
      timestamp
      hasSubComments
      likedCount
      liked
      status
      __typename
    }
    pcursorV2
    rootComments {
      commentId
      authorId
      authorName
      content
      headurl
      timestamp
      likedCount
      realLikedCount
      liked
      status
      authorLiked
      subCommentCount
      subCommentsPcursor
      subComments {
        commentId
        authorId
        authorName
        content
        headurl
        timestamp
        likedCount
        realLikedCount
        liked
        status
        authorLiked
        replyToUserName
        replyTo
        __typename
      }
      __typename
    }
    __typename
  }
}
"""
