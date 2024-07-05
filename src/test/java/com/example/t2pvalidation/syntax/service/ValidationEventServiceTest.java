package com.example.t2pvalidation.syntax.service;

import com.example.t2pvalidation.utils.ValidationResult;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.context.junit.jupiter.SpringExtension;

import static org.junit.jupiter.api.Assertions.*;

@ExtendWith(SpringExtension.class)
@SpringBootTest
class ValidationEventServiceTest {

    @Autowired
    private ValidationEventService validationEventService;

    @Test
    void testValidateBpmnEvents_withValidEvents() {
        String filePath = "src/main/resources/test/bpmn/perfect_model.bpmn";

        ValidationResult result = validationEventService.validateBpmnEvents(filePath);
        assertEquals("completed", result.getValidationStatus());
        assertTrue(result.getErrors().isEmpty());
        assertTrue(result.getWarnings().isEmpty());
    }

    @Test
    void testValidateBpmnEvents_withMissingStartEvent() {
        String filePath = "src/main/resources/test/bpmn/event/false_event_missing_start.bpmn";

        ValidationResult result = validationEventService.validateBpmnEvents(filePath);
        assertEquals("failed", result.getValidationStatus());
        assertFalse(result.getErrors().isEmpty());
        assertTrue(result.getErrors().stream().anyMatch(e -> e.toString().contains("No Start Event found")));
    }

    @Test
    void testValidateBpmnEvents_withMissingEndEvent() {
        String filePath = "src/main/resources/test/bpmn/event/false_event_missing_end.bpmn";

        ValidationResult result = validationEventService.validateBpmnEvents(filePath);
        assertEquals("failed", result.getValidationStatus());
        assertFalse(result.getErrors().isEmpty());
        assertTrue(result.getErrors().stream().anyMatch(e -> e.toString().contains("No End Event found")));
    }

    @Test
    void testValidateBpmnEvents_withUnnamedEvents() {
        String filePath = "src/main/resources/test/bpmn/event/false_event_unnamed.bpmn";

        ValidationResult result = validationEventService.validateBpmnEvents(filePath);
        assertEquals("failed", result.getValidationStatus());
        assertFalse(result.getErrors().isEmpty());
        assertTrue(result.getErrors().stream().anyMatch(e -> e.toString().contains("has no name")));
    }
}
