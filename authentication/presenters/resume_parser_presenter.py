from rest_framework import status
from rest_framework.response import Response


class ResumeParserPresenter:
    def successful_parse_and_store_response(self):
        return Response({"success": True}, status=status.HTTP_200_OK)

    def invalid_request_response(self, message="Invalid request"):
        return Response(
            {"success": False, "error_code": "INVALID_REQUEST", "message": message},
            status=status.HTTP_400_BAD_REQUEST,
        )

    def no_text_extracted_response(self):
        return Response(
            {
                "success": False,
                "error_code": "NO_TEXT_EXTRACTED",
                "message": "No text could be extracted from file.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    def parsing_error_response(self):
        return Response(
            {"success": False, "error_code": "PARSING_ERROR", "message": "Resume parsing failed."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
