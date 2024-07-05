package com.example.t2pvalidation.syntax.service;

import com.example.t2pvalidation.utils.ValidationResult;
import org.camunda.bpm.model.bpmn.Bpmn;
import org.camunda.bpm.model.bpmn.BpmnModelInstance;
import org.camunda.bpm.model.bpmn.instance.ServiceTask;
import org.camunda.bpm.model.bpmn.instance.UserTask;
import org.camunda.bpm.model.xml.ModelParseException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.io.File;
import java.util.ArrayList;
import java.util.List;

@Service
public class ValidationTaskService {

    private static final Logger logger = LoggerFactory.getLogger(ValidationTaskService.class);

    public ValidationResult validateTasks(String bpmnFilePath) {
        ValidationResult validationResult = new ValidationResult();
        List<Object> errors = new ArrayList<>();
        List<Object> warnings = new ArrayList<>();

        BpmnModelInstance modelInstance = null;
        try {
            modelInstance = Bpmn.readModelFromFile(new File(bpmnFilePath));
        } catch (ModelParseException e) {
            logger.warn("Handled BPMN parsing issue: " + e.getMessage());
            warnings.add("BPMN parsing issues detected: " + e.getMessage());
            validationResult.setWarnings(warnings);
        }

        if (modelInstance != null) {
            try {
                validateUserTasks(modelInstance, errors);
                validateServiceTasks(modelInstance, errors);
            } catch (Exception e) {
                logger.error("Validation error while processing tasks: ", e);
                errors.add("Validation error while processing tasks: " + e.getMessage());
            }

            validationResult.setErrors(errors);
            validationResult.setWarnings(warnings);
            validationResult.setValidationStatus(errors.isEmpty() ? "completed" : "failed");

        } else {
            validationResult.setValidationStatus("failed");
            validationResult.setErrorMessage("Model instance could not be parsed.");
        }

        return validationResult;
    }

    private void validateUserTasks(BpmnModelInstance modelInstance, List<Object> errors) {
        for (UserTask userTask : modelInstance.getModelElementsByType(UserTask.class)) {
            if (userTask.getName() == null || userTask.getName().isEmpty()) {
                errors.add("User Task with ID " + userTask.getId() + " has no name.");
            }
            if (userTask.getCamundaAssignee() == null || userTask.getCamundaAssignee().isEmpty()) {
                errors.add("User Task with ID " + userTask.getId() + " has no assignee.");
            }
        }
    }

    private void validateServiceTasks(BpmnModelInstance modelInstance, List<Object> errors) {
        for (ServiceTask serviceTask : modelInstance.getModelElementsByType(ServiceTask.class)) {
            if (serviceTask.getName() == null || serviceTask.getName().isEmpty()) {
                errors.add("Service Task with ID " + serviceTask.getId() + " has no name.");
            }
            if (serviceTask.getCamundaType() == null || serviceTask.getCamundaType().isEmpty()) {
                errors.add("Service Task with ID " + serviceTask.getId() + " has no implementation type.");
            }
        }
    }
}
