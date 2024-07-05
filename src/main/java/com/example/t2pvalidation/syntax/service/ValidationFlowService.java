package com.example.t2pvalidation.syntax.service;

import com.example.t2pvalidation.utils.ValidationResult;
import org.camunda.bpm.model.bpmn.Bpmn;
import org.camunda.bpm.model.bpmn.BpmnModelInstance;
import org.camunda.bpm.model.bpmn.instance.FlowNode;
import org.camunda.bpm.model.bpmn.instance.StartEvent;
import org.camunda.bpm.model.bpmn.instance.EndEvent;
import org.camunda.bpm.model.xml.ModelParseException;
import org.camunda.bpm.model.xml.instance.ModelElementInstance;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.io.File;
import java.util.ArrayList;
import java.util.List;

@Service
public class ValidationFlowService {

    private static final Logger logger = LoggerFactory.getLogger(ValidationFlowService.class);

    public ValidationResult validateNoUnboundFlows(String filePath) {
        ValidationResult validationResult = new ValidationResult();
        List<Object> errors = new ArrayList<>();
        List<Object> warnings = new ArrayList<>();

        BpmnModelInstance modelInstance = null;
        try {
            modelInstance = Bpmn.readModelFromFile(new File(filePath));
        } catch (ModelParseException e) {
            logger.warn("Handled BPMN parsing issue: " + e.getMessage());
            warnings.add("BPMN parsing issues detected: " + e.getMessage());
            validationResult.setWarnings(warnings);
        }

        if (modelInstance != null) {
            try {
                for (ModelElementInstance elementInstance : modelInstance.getModelElementsByType(FlowNode.class)) {
                    if (elementInstance instanceof FlowNode) {
                        FlowNode flowNode = (FlowNode) elementInstance;

                        // Check if the node is not a StartEvent and has no incoming flows
                        if (!(flowNode instanceof StartEvent) && flowNode.getIncoming().isEmpty()) {
                            errors.add("FlowNode with ID " + flowNode.getId() + " has no incoming flows.");
                        }

                        // Check if the node is not an EndEvent and has no outgoing flows
                        if (!(flowNode instanceof EndEvent) && flowNode.getOutgoing().isEmpty()) {
                            errors.add("FlowNode with ID " + flowNode.getId() + " has no outgoing flows.");
                        }
                    }
                }
            } catch (Exception e) {
                logger.error("Validation error: ", e);
                errors.add("Validation error: " + e.getMessage());
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
}
