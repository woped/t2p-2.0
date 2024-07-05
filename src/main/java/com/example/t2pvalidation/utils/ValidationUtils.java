package com.example.t2pvalidation.utils;

import org.xml.sax.SAXParseException;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class ValidationUtils {

    public static Map<String, Object> mapValidationResult(ValidationResult validationResult) {
        Map<String, Object> result = new HashMap<>();
        result.put("validationStatus", validationResult.getValidationStatus());

        if ("failed".equals(validationResult.getValidationStatus())) {
            result.put("errorMessage", validationResult.getErrorMessage());
            result.put("errors", categorizeErrors(validationResult.getErrors()));
            return result;
        }

        result.put("errors", categorizeErrors(validationResult.getErrors()));
        result.put("warnings", categorizeWarnings(validationResult.getWarnings()));
        result.put("summary", createSummary(validationResult.getErrors(), validationResult.getWarnings()));

        return result;
    }

    private static List<Map<String, String>> categorizeErrors(List<Object> errors) {
        List<Map<String, String>> categorizedErrors = new ArrayList<>();
        if (errors != null) {
            for (Object error : errors) {
                Map<String, String> errorDetails = new HashMap<>();
                if (error instanceof SAXParseException) {
                    SAXParseException saxError = (SAXParseException) error;
                    errorDetails.put("type", "syntax");
                    errorDetails.put("line", String.valueOf(saxError.getLineNumber()));
                    errorDetails.put("elementId", extractElementId(saxError));
                    errorDetails.put("message", saxError.getMessage());
                    errorDetails.put("suggestion", "Please fix the syntax error.");
                } else if (error instanceof String) {
                    errorDetails.put("type", "syntax");
                    errorDetails.put("message", (String) error);
                    errorDetails.put("suggestion", "Please fix the configuration error.");
                }
                categorizedErrors.add(errorDetails);
            }
        }
        return categorizedErrors;
    }

    private static List<Map<String, String>> categorizeWarnings(List<Object> warnings) {
        List<Map<String, String>> categorizedWarnings = new ArrayList<>();
        if (warnings != null) {
            for (Object warning : warnings) {
                Map<String, String> warningDetails = new HashMap<>();
                if (warning instanceof SAXParseException) {
                    SAXParseException saxWarning = (SAXParseException) warning;
                    warningDetails.put("type", "complexity");
                    warningDetails.put("elementId", extractElementId(saxWarning));
                    warningDetails.put("message", saxWarning.getMessage());
                    warningDetails.put("suggestion", "Consider reviewing the complexity.");
                } else if (warning instanceof String) {
                    warningDetails.put("type", "syntax");
                    warningDetails.put("message", (String) warning);
                    warningDetails.put("suggestion", "Consider reviewing the BPMN configuration.");
                }
                categorizedWarnings.add(warningDetails);
            }
        }
        return categorizedWarnings;
    }

    private static Map<String, Integer> createSummary(List<Object> errors, List<Object> warnings) {
        Map<String, Integer> summary = new HashMap<>();
        summary.put("totalErrors", errors == null ? 0 : errors.size());
        summary.put("totalWarnings", warnings == null ? 0 : warnings.size());
        return summary;
    }

    private static String extractElementId(SAXParseException exception) {
        String message = exception.getMessage();
        String elementId = "unknown";

        if (message != null) {
            String[] patterns = {"The element type \"", "Element \"", "Element type \""};
            for (String pattern : patterns) {
                int startIndex = message.indexOf(pattern);
                if (startIndex != -1) {
                    startIndex += pattern.length();
                    int endIndex = message.indexOf("\"", startIndex);
                    if (endIndex > startIndex) {
                        elementId = message.substring(startIndex, endIndex);
                        break;
                    }
                }
            }

            if ("unknown".equals(elementId)) {
                String nsPattern = "http://www.omg.org/spec/BPMN/20100524/MODEL";
                if (message.contains(nsPattern)) {
                    elementId = nsPattern;
                }
            }
        }
        return elementId;
    }
}
